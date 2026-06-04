# Memory-Worker Remote Control (v2 — n8n bot extension) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Supersedes** the v1 local-poller plan (same path, git history). v1's `memory-bot.py` getUpdates poller conflicts with the existing `setWebhook` bot on the monitoring token (Telegram 409).

**Goal:** Pilot the memory-worker from an iPhone by **extending the existing n8n Telegram bot** (`memory-telegram-bot.json`) with `/memory_start /memory_stop /memory_run /memory_fix`; n8n (Sese) invokes `memctl` on waza via a **forced-command SSH key over Tailscale**. Keep the v1 lock-hardening (root-cause fix) and migrate the worker to sudo-free systemd-user units.

**Architecture:** Telegram → existing n8n webhook (monitoring token). The Code handler classifies action-vs-read; a **Switch** routes action commands to an `n8n-nodes-base.ssh` node that runs `memctl <action>` on waza `100.64.0.1`. waza pins the SSH key to a forced-command wrapper (`memctl-remote.sh`, allow-list of 5 subcommands). Read commands (status/health/last/help) are unchanged. The worker `service`+`timer` migrate system→user (linger), so `memctl`'s `systemctl --user` works without sudo.

**Tech Stack:** Bash (`memctl`, `memctl-remote`, `set -uo pipefail`), systemd-user + linger, `ansible.posix.authorized_key`, n8n 2.7.3 (Switch + SSH nodes, MCP `n8n_update_full_workflow`), Tailscale (waza=`100.64.0.1`).

**Spec:** `docs/superpowers/specs/2026-06-04-memory-worker-remote-control-design.md`.

---

## Grounding facts (verified 2026-06-04)
- **Already committed & valid** (do NOT rebuild): `index.py.j2` PID-validated lock (`2ec1612`); `memctl.sh` (`25475d2`+`cfecfdd`) — defaults pin units `llamaindex-memory-worker.{timer,service}`, sudo-free, `systemctl --user`; user-unit templates `memory-worker.{service,timer}.user.j2` (`5818c4e`); tests `test_lock.py`, `test_memctl.sh`.
- **Obsolete (to delete this plan)**: `files/memory-bot.py` (`db1d9a4`), `templates/memory-bot.service.user.j2` (part of `5818c4e`), `tests/test_memory_bot.py`, its line in `tests/run.sh`.
- **n8n**: `javisi_n8n` = `ghcr.io/mobutoo/n8n-enterprise:2.7.3`. Container **reaches waza `100.64.0.1:22`** (tested: `node net.connect` → OK). Existing bot uses IF `typeVersion:2` (Validate Secret, Should Reply) and works **live** → do not add NEW IF v2 (use Switch), keep existing.
- **Workflow JSON** `scripts/n8n-workflows/memory-telegram-bot.json`: id-less canonical source (no top-level `id`/`active`). Deploy via **MCP `n8n_update_full_workflow` by live id** — NOT `deploy-workflow.sh` (requires id + hard-blocks IF v2 at `:76`). Auth already in place: webhook `secret_token` + `chat.id === TELEGRAM_MONITORING_CHAT_ID` (covers actions). Reuses `TELEGRAM_MONITORING_BOT_TOKEN`/`_CHAT_ID` env (no new secrets).
- **Ansible** `roles/llamaindex-memory-worker/`: `tasks/main.yml` deploys SYSTEM units (`:160-183`); handlers `Reload systemd` + `Restart llamaindex-memory-worker timer`. 7 tasks `notify: Restart llamaindex-memory-worker timer` (`:62,72,136,146,158` + the 2 unit tasks). `defaults/main.yml` clean (no telegram/bot/uid vars). `memory_worker_user`=`mobuone` (uid 1000), linger off.
- **`deploy-workflow.sh`** is the wrong tool here (see above) — the plan uses the MCP path.

---

## File Structure
| Path | New/Mod/Del | Responsibility |
|---|---|---|
| `roles/llamaindex-memory-worker/files/memory-bot.py` | **DELETE** | Obsolete getUpdates poller (conflicts with webhook). |
| `roles/llamaindex-memory-worker/templates/memory-bot.service.user.j2` | **DELETE** | Obsolete bot user-service. |
| `roles/llamaindex-memory-worker/tests/test_memory_bot.py` | **DELETE** | Tests the deleted poller. |
| `roles/llamaindex-memory-worker/tests/run.sh` | MOD | Drop the `test_memory_bot.py` line. |
| `roles/llamaindex-memory-worker/files/memctl-remote.sh` | **NEW** | Forced-command SSH wrapper: allow-list {status,start,stop,run,fix} → `memctl.sh`. Sets XDG_RUNTIME_DIR + DBUS bus. |
| `roles/llamaindex-memory-worker/tests/test_memctl_remote.sh` | **NEW** | Allow-list + injection-rejection tests (stub memctl). |
| `roles/llamaindex-memory-worker/defaults/main.yml` | MOD | `memory_worker_uid`, `memory_worker_user_unit_dir`, `memory_worker_ssh_pubkey` (default ''). |
| `roles/llamaindex-memory-worker/tasks/main.yml` | MOD | Uninstall system units; deploy memctl+memctl-remote; install user units (`enable --now` timer); authorized_key forced-command; reconcile notifies. |
| `roles/llamaindex-memory-worker/handlers/main.yml` | MOD | `Reload systemd (system)` + `Reload systemd (user)`; drop dead timer-restart handler. |
| `inventory/group_vars/all/main.yml` | MOD | `memory_worker_ssh_pubkey` from a non-secret var (public key). |
| `scripts/n8n-workflows/memory-telegram-bot.json` | MOD | Add action classifier + Switch + SSH node + reply formatter. |

## Conventions
- Static files (`memctl*.sh`) read ALL config from ENV → unit-testable, deployed via `ansible.builtin.copy`.
- Ansible: FQCN, explicit `changed_when`/`failed_when`, idempotent (0 changed on 2nd run), tags `[llamaindex-memory-worker, memory_remote]`.
- `systemctl --user` tasks: `become: true` + `become_user: "{{ memory_worker_user }}"` + `environment: { XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}" }`.
- n8n: file-first (R3) — edit JSON → `validate_workflow` (R1) → `n8n_update_full_workflow` by id (R11). No new IF v2 (R9). Reinit MCP if `-32000` (R1-bis).
- Tests run on waza: `bash roles/llamaindex-memory-worker/tests/run.sh`.

---

### Task 0 (verify-only — already committed, do NOT rebuild)

- [ ] Confirm the salvaged work is present and green before building on it:

```bash
cd /home/mobuone/VPAI
git log --oneline -1 -- roles/llamaindex-memory-worker/templates/index.py.j2 | grep -q 2ec1612 || echo "WARN: lock-hardening commit not found"
python3 roles/llamaindex-memory-worker/tests/test_lock.py     # expect ALL OK
bash   roles/llamaindex-memory-worker/tests/test_memctl.sh    # expect test_memctl PASS
```
If either fails → STOP and reconcile before proceeding (these are the foundation).

---

### Task 1: Remove obsolete v1 poller artifacts

**Files:** Delete `files/memory-bot.py`, `templates/memory-bot.service.user.j2`, `tests/test_memory_bot.py`; Modify `tests/run.sh`

- [ ] **Step 1: Delete the three obsolete files**

```bash
cd /home/mobuone/VPAI
git rm roles/llamaindex-memory-worker/files/memory-bot.py \
       roles/llamaindex-memory-worker/templates/memory-bot.service.user.j2 \
       roles/llamaindex-memory-worker/tests/test_memory_bot.py
```

- [ ] **Step 2: Drop the bot test from `run.sh`** — remove only the line `python3 test_memory_bot.py || f=1` (the `test_memctl_remote.sh` line is added in Task 2, so every commit stays green). Result:

```bash
#!/bin/bash
set -uo pipefail; cd "$(dirname "$0")"; f=0
bash test_memctl.sh || f=1
python3 test_lock.py || f=1
[ "$f" = 0 ] && echo "ALL ROLE TESTS PASS" || { echo "ROLE TESTS FAILED"; exit 1; }
```

- [ ] **Step 3: Verify no dangling references** to the deleted files

```bash
grep -rn "memory-bot\|memory_bot" roles/llamaindex-memory-worker/ \
  | grep -v "templates/run-and-report\|\.env.j2\|# " || echo "no dangling refs (the bot service is not yet wired in tasks/main.yml — confirm)"
```
Expected: only comments / unrelated matches. The bot service was never wired into `tasks/main.yml` (v1 Task 6 unexecuted), so nothing else to clean.

- [ ] **Step 4: Commit**

```bash
git add -A roles/llamaindex-memory-worker/tests/run.sh
git commit -m "chore(memory-worker): drop obsolete v1 getUpdates poller (conflicts with n8n webhook bot)"
```

---

### Task 2: `memctl-remote.sh` — forced-command SSH wrapper (TDD)

**Files:** Create `roles/llamaindex-memory-worker/files/memctl-remote.sh`, `roles/llamaindex-memory-worker/tests/test_memctl_remote.sh`

- [ ] **Step 1: Write the failing test** (stubs `memctl.sh` to capture the passed arg; the wrapper path to memctl is overridable via env for the test)

```bash
# roles/llamaindex-memory-worker/tests/test_memctl_remote.sh
#!/bin/bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; WRAP="$HERE/../files/memctl-remote.sh"
TMP="$(mktemp -d)"
# Stub memctl: record the argument it was called with.
STUB="$TMP/memctl.sh"
printf '#!/bin/bash\necho "MEMCTL_CALLED:$1" > "%s/called"\n' "$TMP" > "$STUB"; chmod +x "$STUB"
export MEMCTL_BIN="$STUB"   # wrapper must honor this override (default = real path)
fail=0; ok(){ [ "$1" = 1 ] && echo "  ok: $2" || { echo "  FAIL: $2"; fail=1; }; }
called(){ cat "$TMP/called" 2>/dev/null || echo NONE; }

# valid action → memctl run
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="run" bash "$WRAP" >/dev/null 2>&1
ok "$([ "$(called)" = "MEMCTL_CALLED:run" ] && echo 1)" "valid 'run' dispatches memctl run"

# injection with glued ';' → DENIED (awk \$1 = 'status;' → no case match), memctl NOT called
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="status; rm -rf /" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -ne 0 ] && echo 1)" "'status; rm' denied (glued ;), memctl not called"

# space before ';' → \$1='status' → runs status, drops the rest (rm never runs)
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="status ; rm -rf /" bash "$WRAP" >/dev/null 2>&1
ok "$([ "$(called)" = "MEMCTL_CALLED:status" ] && echo 1)" "'status ; rm' runs only status"

# multiline → denied
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="$(printf 'status\nrm -rf /')" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -ne 0 ] && echo 1)" "multiline input denied"

# unknown command → denied, exit 2
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="evil" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -eq 2 ] && echo 1)" "unknown command denied exit 2"

# empty → denied
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -ne 0 ] && echo 1)" "empty command denied"

rm -rf "$TMP"; [ "$fail" = 0 ] && echo "test_memctl_remote PASS" || { echo "test_memctl_remote FAIL"; exit 1; }
```

- [ ] **Step 2: Run → FAIL** (`memctl-remote.sh` not found)

```bash
bash roles/llamaindex-memory-worker/tests/test_memctl_remote.sh
```

- [ ] **Step 3: Implement `roles/llamaindex-memory-worker/files/memctl-remote.sh`**

```bash
#!/bin/bash
# memctl-remote.sh — forced-command SSH wrapper for memctl.
# Pinned in waza:~mobuone/.ssh/authorized_keys via command="…/memctl-remote.sh".
# Validates SSH_ORIGINAL_COMMAND against an allow-list, then execs memctl.
set -uo pipefail
# SSH non-login session: set the user bus explicitly, else `systemctl --user`
# fails "Failed to connect to bus" even with linger + XDG_RUNTIME_DIR.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
MEMCTL_BIN="${MEMCTL_BIN:-/opt/workstation/ai-memory-worker/memctl.sh}"

cmd="${SSH_ORIGINAL_COMMAND:-}"
# First token of the first line only — any separator (;, &&, |, newline) glued to
# the token or on later lines fails the case match → denied.
cmd="$(printf '%s' "$cmd" | tr -d '\r' | awk 'NR==1{print $1}')"
case "$cmd" in
  status|start|stop|run|fix) exec bash "$MEMCTL_BIN" "$cmd" ;;
  *) echo "denied: '$cmd' not in {status,start,stop,run,fix}" >&2; exit 2 ;;
esac
```

- [ ] **Step 4: Wire the test into `run.sh`** — add the line `bash test_memctl_remote.sh || f=1` (after the `test_memctl.sh` line):

```bash
#!/bin/bash
set -uo pipefail; cd "$(dirname "$0")"; f=0
bash test_memctl.sh || f=1
bash test_memctl_remote.sh || f=1
python3 test_lock.py || f=1
[ "$f" = 0 ] && echo "ALL ROLE TESTS PASS" || { echo "ROLE TESTS FAILED"; exit 1; }
```

- [ ] **Step 5: Run → PASS**

```bash
chmod +x roles/llamaindex-memory-worker/files/memctl-remote.sh
bash roles/llamaindex-memory-worker/tests/test_memctl_remote.sh   # expect: test_memctl_remote PASS
bash -n roles/llamaindex-memory-worker/files/memctl-remote.sh && echo "syntax OK"
bash roles/llamaindex-memory-worker/tests/run.sh                  # expect: ALL ROLE TESTS PASS
```

> Note: `MEMCTL_BIN` is honored ONLY by `memctl-remote.sh` (for unit-testing); the target `memctl.sh` keeps its hardcoded unit names. The prod default `/opt/workstation/ai-memory-worker/memctl.sh` = `{{ memory_worker_install_dir }}/memctl.sh` (where Task 3 deploys it). Spec §4.2 hardcodes the path; this `MEMCTL_BIN` override is a deliberate, beneficial addition — do not "fix" it back.

- [ ] **Step 6: Commit**

```bash
git add roles/llamaindex-memory-worker/files/memctl-remote.sh roles/llamaindex-memory-worker/tests/test_memctl_remote.sh roles/llamaindex-memory-worker/tests/run.sh
git commit -m "feat(memory-worker): memctl-remote.sh — forced-command SSH wrapper (allow-list, sudo-free)"
```

---

### Task 3: Ansible — migrate system→user units + deploy memctl/wrapper + authorized_key

**Files:** Modify `roles/llamaindex-memory-worker/defaults/main.yml`, `tasks/main.yml`, `handlers/main.yml`, `inventory/group_vars/all/main.yml`

- [ ] **Step 1: Add role defaults** — append to `roles/llamaindex-memory-worker/defaults/main.yml`:

```yaml
# Remote control (v2): systemd-user migration + SSH forced-command from n8n
memory_worker_uid: 1000                                   # uid of mobuone (XDG_RUNTIME_DIR)
memory_worker_user_unit_dir: "/home/{{ memory_worker_user }}/.config/systemd/user"
memory_worker_ssh_pubkey: "{{ memory_worker_ssh_pubkey_value | default('') }}"  # n8n-memctl public key; empty = skip authorized_key
```

- [ ] **Step 2: Expose the public key var** — add to `inventory/group_vars/all/main.yml` (public key is NOT a secret; no vault needed):

```yaml
# n8n-memctl SSH public key (forced-command to memctl-remote.sh on waza).
# Filled after Task 5 keygen. Empty until then → authorized_key task is skipped.
memory_worker_ssh_pubkey_value: ""
```

- [ ] **Step 3: Reconcile handlers** — rewrite `roles/llamaindex-memory-worker/handlers/main.yml`:

```yaml
---
# llamaindex-memory-worker — handlers
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
    DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/user/{{ memory_worker_uid }}/bus"
```
The old `Restart llamaindex-memory-worker timer` handler is removed (the 7 notifies are rewired in Step 4; user-units are oneshot/timer — a forced restart is meaningless).

- [ ] **Step 4: Rewire the 7 `notify: Restart llamaindex-memory-worker timer`** in `tasks/main.yml` (`:62,72,136,146,158` + the 2 unit tasks at `:168,180`):
  - On `Deploy memory worker environment file` (`:62`), `config` (`:72`), `run-and-report` (`:136`), `wait-calm` (`:146`), `webhook secret` (`:158`) → **remove the `notify:`** (these are read at the next worker run; no restart needed for a timer-driven oneshot).
  - The 2 unit-template tasks (`:160-183`) are DELETED in Step 5.

- [ ] **Step 5: Replace the 2 system-unit deploy tasks (`:160-183`)** with uninstall + user-unit install. Delete both `Deploy memory worker systemd service/timer` tasks and any later `Enable and start … timer` task, and insert:

```yaml
- name: Stat legacy SYSTEM unit files
  ansible.builtin.stat:
    path: "/etc/systemd/system/{{ item }}"
  become: true
  loop:
    - "{{ memory_worker_service_name }}.service"
    - "{{ memory_worker_timer_name }}.timer"
  register: legacy_unit_stat
  tags: [llamaindex-memory-worker, memory_remote]

- name: Disable + stop legacy SYSTEM units (only if present — keeps 2nd run quiet & idempotent)
  ansible.builtin.systemd:
    name: "{{ item.item }}"
    state: stopped
    enabled: false
  become: true
  loop: "{{ legacy_unit_stat.results }}"
  when: item.stat.exists
  loop_control:
    label: "{{ item.item }}"
  tags: [llamaindex-memory-worker, memory_remote]

- name: Remove legacy SYSTEM unit files
  ansible.builtin.file:
    path: "/etc/systemd/system/{{ item }}"
    state: absent
  become: true
  loop:
    - "{{ memory_worker_service_name }}.service"
    - "{{ memory_worker_timer_name }}.timer"
  notify: Reload systemd (system)
  tags: [llamaindex-memory-worker, memory_remote]

- name: Enable linger for {{ memory_worker_user }} (user units run without login)
  ansible.builtin.command: "loginctl enable-linger {{ memory_worker_user }}"
  become: true
  args:
    creates: "/var/lib/systemd/linger/{{ memory_worker_user }}"
  tags: [llamaindex-memory-worker, memory_remote]

- name: Ensure user systemd unit dir
  ansible.builtin.file:
    path: "{{ memory_worker_user_unit_dir }}"
    state: directory
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0755"
  become: true
  tags: [llamaindex-memory-worker, memory_remote]

- name: Deploy USER units (names MUST match memctl defaults)
  ansible.builtin.template:
    src: "{{ item.src }}"
    dest: "{{ memory_worker_user_unit_dir }}/{{ item.dest }}"
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0644"
  become: true
  loop:
    - { src: "memory-worker.service.user.j2", dest: "{{ memory_worker_service_name }}.service" }
    - { src: "memory-worker.timer.user.j2",   dest: "{{ memory_worker_timer_name }}.timer" }
  notify: Reload systemd (user)
  tags: [llamaindex-memory-worker, memory_remote]

- name: Deploy memctl.sh + memctl-remote.sh
  ansible.builtin.copy:
    src: "{{ item }}"
    dest: "{{ memory_worker_install_dir }}/{{ item }}"
    owner: "{{ memory_worker_user }}"
    group: "{{ memory_worker_user }}"
    mode: "0755"
  become: true
  loop:
    - memctl.sh
    - memctl-remote.sh
  tags: [llamaindex-memory-worker, memory_remote]

- name: Ensure the user systemd instance is running (creates /run/user/{{ memory_worker_uid }} after fresh linger)
  ansible.builtin.systemd:
    name: "user@{{ memory_worker_uid }}.service"
    state: started
  become: true
  tags: [llamaindex-memory-worker, memory_remote]

- name: Flush handlers so daemon-reload happens before enable
  ansible.builtin.meta: flush_handlers

- name: Enable + start USER timer (kills the dormancy root cause — non-negotiable)
  ansible.builtin.systemd:
    name: "{{ memory_worker_timer_name }}.timer"
    scope: user
    enabled: true
    state: started
    daemon_reload: true
  become: true
  become_user: "{{ memory_worker_user }}"
  environment:
    XDG_RUNTIME_DIR: "/run/user/{{ memory_worker_uid }}"
    DBUS_SESSION_BUS_ADDRESS: "unix:path=/run/user/{{ memory_worker_uid }}/bus"
  tags: [llamaindex-memory-worker, memory_remote]

- name: Install n8n-memctl forced-command SSH key
  ansible.posix.authorized_key:
    user: "{{ memory_worker_user }}"
    key: "{{ memory_worker_ssh_pubkey }}"
    state: present
    exclusive: false
    key_options: 'command="{{ memory_worker_install_dir }}/memctl-remote.sh",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding'
  become: true
  when: memory_worker_ssh_pubkey | length > 0
  tags: [llamaindex-memory-worker, memory_remote]
```

> `memory_worker_install_dir` is an existing role var (where memctl.sh already lives — confirm its value in defaults; the spec assumes `/opt/workstation/ai-memory-worker`). If `memctl.sh`'s hardcoded default path (`/opt/workstation/ai-memory-worker/memctl.sh`) differs from `memory_worker_install_dir`, align them (the wrapper uses the hardcoded default unless `MEMCTL_BIN` is set).
> `ansible.builtin.systemd` `scope: user` needs ansible-core ≥2.13 — verify (`ansible --version`); else fall back to `ansible.builtin.command: "systemctl --user …"` with the same `become_user`+`environment` and explicit `changed_when`.

- [ ] **Step 6: Add `memory_remote` tags** to the EXISTING tasks that carry the v2-critical changes so `--tags memory_remote` doesn't skip them: `Deploy memory worker environment file` (`:53`), `Deploy memory worker index script` (`:83`), and the `Verify memory worker script imports` py_compile task (find it after `:183`). Add `tags: [llamaindex-memory-worker, memory_remote]` to each.

- [ ] **Step 7: Lint**

```bash
cd /home/mobuone/VPAI && source .venv/bin/activate && make lint
```
Expected: pass (FQCN, changed_when present, no dangling notify).

- [ ] **Step 8: Commit**

```bash
git add roles/llamaindex-memory-worker/defaults/main.yml roles/llamaindex-memory-worker/tasks/main.yml roles/llamaindex-memory-worker/handlers/main.yml inventory/group_vars/all/main.yml
git commit -m "feat(memory-worker): migrate to systemd-user units + forced-command SSH key (no bot, no sudo)"
```

---

### Task 4: Extend the n8n workflow JSON (file-first)

**Files:** Modify `scripts/n8n-workflows/memory-telegram-bot.json`

> R1-bis: if the n8n-docs MCP returns `-32000`, reinit before validating. R8: confirm the exact `n8n-nodes-base.ssh` and `n8n-nodes-base.switch` param schemas via `mcp__n8n-docs__get_node` before finalizing node JSON.

- [ ] **Step 1: Extend the `Handle Command` Code node** — two edits:
  - **(a) Add the action branch** after the existing `/memory_help` branch and before the final `else` (unknown):
    ```javascript
      } else if (['/memory_start','/memory_stop','/memory_run','/memory_fix'].includes(cmd)) {
        // Action command: defer to the SSH branch. Emit the bare action keyword that
        // memctl-remote.sh's allow-list expects (status|start|stop|run|fix).
        return [{ json: { skip: false, is_action: true, action: cmd.replace('/memory_', ''), chat_id: chatId } }];
    ```
  - **(b) CRITICAL — set `is_action: false` on ALL THREE other return shapes** (the Code node currently has 3 returns; a strict-boolean Switch routes `undefined` to NEITHER output, dropping unauthorized/unknown items so `Respond 200` never fires → Telegram retry storm). Patch each:
    - unauthorized chat: `return [{ json: { skip: true, is_action: false, reason: 'unauthorized_chat', chat_id: chatId } }];`
    - unknown command: `return [{ json: { skip: true, is_action: false, reason: 'unknown_command', text } }];`
    - final read return: `return [{ json: { skip: false, is_action: false, chat_id: chatId, reply_text: reply } }];`

- [ ] **Step 2: Add a `Switch` fork after `Handle Command`** — insert a **Switch** node `Action or Read?` (NOT a new IF v2 — R9). Configure with an explicit rule `={{ $json.is_action }}` **is true** → output 0 (SSH branch), and a **`fallbackOutput`** (catch-all) → output 1 (read branch). The fallback guarantees `is_action:false` AND any unexpected `undefined` both reach the read path (which `Should Reply?` already filters on `skip`). Rewire: `Handle Command` → `Action or Read?`; output 1 (fallback/read) → `Should Reply?` (unchanged downstream → Send Reply / Respond 200); output 0 (action) → `Run memctl (SSH)`.
  - After the edit, **trace it**: an unauthorized-chat item (`skip:true, is_action:false`) must reach `Respond 200` via the read branch, exactly as today. Confirm no item type is dropped.

- [ ] **Step 3: Add the SSH node** `Run memctl (SSH)` (`n8n-nodes-base.ssh`): resource/operation = execute command; `command = {{ $json.action }}`; host `100.64.0.1`, port `22`, username `mobuone`; credential = SSH private key (referenced by id — **placeholder now**, real id wired in Task 5); short timeout (~10000 ms); `onError: continueRegularOutput`. Forced-command on waza re-validates, so even a bad `command` is contained.

- [ ] **Step 4: Add `Format Action Reply` Code node** — turns memctl stdout into a Telegram message; tolerates malformed JSON:

```javascript
const a = $('Handle Command').first().json.action;
const raw = ($input.first().json.stdout || $input.first().json.stderr || '(aucune sortie — waza injoignable ?)').trim();
let reply;
if (a === 'status') {
  try { const d = JSON.parse(raw);
    reply = `📊 memory-worker\nspool: ${d.spool_depth} | lock pid=${d.lock_pid||'-'} alive=${d.lock_alive}\nqdrant: ${d.qdrant_points} pts (joignable=${d.qdrant_reachable})\ntimer: ${d.timer_enabled}/${d.timer_active}`;
  } catch (e) { reply = raw; }
} else { reply = `✅ /memory_${a}\n${raw}`; }
return [{ json: { skip: false, chat_id: $('Handle Command').first().json.chat_id, reply_text: reply } }];
```
Wire `Run memctl (SSH)` → `Format Action Reply` → `Send Reply` (existing) AND `Respond 200` (existing). **Ack timing**: ensure `Respond 200` is reachable without waiting on a slow SSH — the ~10s SSH timeout bounds the webhook response under Telegram's retry window (spec §4.3.6).

- [ ] **Step 5: Validate (R1)** — offline structural sanity (no live id needed):

```bash
python3 -c "import json; d=json.load(open('scripts/n8n-workflows/memory-telegram-bot.json')); \
print('nodes:', len(d['nodes'])); \
print('new IF v2:', [n['name'] for n in d['nodes'] if n.get('type')=='n8n-nodes-base.if' and n.get('typeVersion',1)>=2])"
```
Expected: the IF-v2 list shows ONLY the 2 pre-existing nodes (`Validate Telegram Secret`, `Should Reply?`) — no new ones.
Then (live, Task 5) `mcp__n8n-docs__n8n_validate_workflow` → 0 blocking errors.

- [ ] **Step 6: Commit** (structure only; credential id + deploy in Task 5)

```bash
git add scripts/n8n-workflows/memory-telegram-bot.json
git commit -m "feat(n8n): memory-bot — add /memory_{start,stop,run,fix} via Switch + SSH→memctl (R9-safe)"
```

---

### Task 5: Provision + deploy + live verification (HUMAN-GATED)

> This task touches prod (waza deploy + live n8n). Each sub-step that needs a human secret/credential is flagged. The executor surfaces commands; the human runs the gated ones via `!`.

- [ ] **Step 1 (human): Generate the n8n-memctl SSH keypair**

```bash
ssh-keygen -t ed25519 -N "" -C "n8n-memctl" -f /tmp/n8n-memctl-key
cat /tmp/n8n-memctl-key.pub      # → paste into memory_worker_ssh_pubkey_value (inventory)
```

- [ ] **Step 2 (human): Create the n8n SSH credential** (UI or API) from `/tmp/n8n-memctl-key` (private). Note its **credential id** → wire it into the `Run memctl (SSH)` node in the JSON (replace the placeholder). Delete `/tmp/n8n-memctl-key*` after import.

- [ ] **Step 3: Set the public key var** — put the `.pub` string in `inventory/group_vars/all/main.yml: memory_worker_ssh_pubkey_value`, commit.

- [ ] **Step 4: Deploy to waza** (check-mode first)

```bash
source .venv/bin/activate
ansible-playbook playbooks/hosts/workstation.yml --tags memory_remote --check --diff   # review: system units removed, user units added, linger, authorized_key
make deploy-workstation                                                                 # or the tagged playbook without --check
```

- [ ] **Step 5: Verify the migration live (no sudo)**

```bash
export XDG_RUNTIME_DIR=/run/user/1000
systemctl --user is-enabled llamaindex-memory-worker.timer   # expect: enabled
systemctl --user is-active  llamaindex-memory-worker.timer   # expect: active
ls /etc/systemd/system/llamaindex-memory-worker.* 2>&1        # expect: No such file (system units gone)
set -a; . /opt/workstation/configs/ai-memory-worker/memory-worker.env; set +a
/opt/workstation/ai-memory-worker/memctl.sh status           # expect: JSON, qdrant_reachable true
grep -c 'command=.*memctl-remote.sh' ~/.ssh/authorized_key*  # expect: >=1
```

- [ ] **Step 6 (decisive): Standalone SSH path test from Sese** — proves `systemctl --user` works in a non-login SSH session (the forced-command path), independent of Telegram:

```bash
ssh -i ~/.ssh/seko-vpn-deploy -p 804 mobuone@100.64.0.14 \
  'ssh -i /path/to/n8n-memctl-key -o StrictHostKeyChecking=accept-new mobuone@100.64.0.1 status'
# expect: memctl status JSON. Then test denial:
#   ... mobuone@100.64.0.1 "status; rm -rf /"   → "denied", exit 2
```
If "Failed to connect to bus" → the wrapper's XDG/DBUS export needs adjustment before E2E.

- [ ] **Step 7: Deploy the workflow (R1 → R11)**

```bash
# reinit n8n-docs MCP if -32000, then:
#   n8n_health_check                        → reachable
#   n8n_list_workflows / n8n_get_workflow   → live id of memory-telegram-bot
#   DRIFT CHECK (R3): live JSON == repo JSON modulo id/active? if drift → reconcile live→repo FIRST
#   n8n_validate_workflow(<repo JSON>)      → 0 blocking errors
#   n8n_update_full_workflow(id=<live>, workflow=<repo JSON + real credential id>)
```

- [ ] **Step 8 (human): End-to-end from iPhone** — send to the bot:
  - `/memory_status` → live snapshot (read path, unchanged) ✓
  - `/memory_run` → "✅ /memory_run …" + a run launches (spool drains) ✓
  - `/memory_start` / `/memory_stop` → timer enabled/disabled ✓
  - `/memory_fix` → stale-lock report ✓
  - send a non-action from a foreign chat id → ignored ✓

- [ ] **Step 9: Idempotence** — 2nd deploy = 0 changed

```bash
ansible-playbook playbooks/hosts/workstation.yml --tags memory_remote | tail -3   # expect changed=0
```
> `--tags memory_remote` covers ONLY the migration + remote-control tasks (the venv/pip/most script-deploy tasks stay untagged and are skipped). This is fine on the already-provisioned waza; it is NOT a full-provision path. The `changed=0` assertion therefore covers the tagged subset only.

- [ ] **Step 10: Final commit** (credential id wiring + any tweak)

```bash
git add -A scripts/n8n-workflows/memory-telegram-bot.json inventory/group_vars/all/main.yml
git commit -m "feat(memory-worker): wire n8n SSH credential id + public key; deploy verified" || echo "nothing to commit"
```

---

## Done-Definition
- [ ] `bash roles/llamaindex-memory-worker/tests/run.sh` → ALL ROLE TESTS PASS (memctl, memctl-remote, lock).
- [ ] `make lint` passes.
- [ ] Deploy: system units gone; user timer enabled+active; linger on; forced-command key present once.
- [ ] Standalone SSH `… mobuone@100.64.0.1 status` returns JSON; `"status; rm"` denied.
- [ ] Workflow: only 2 pre-existing IF v2 nodes; `validate_workflow` 0 blocking; updated by live id.
- [ ] iPhone: 4 action commands + existing read commands all work; foreign chat ignored.
- [ ] 2nd deploy = `changed=0`.

## Rollback
Per-commit `git revert`. To revert the unit migration: the system-unit templates + tasks remain in git history — re-add, `systemctl --user disable --now` the user units, `loginctl disable-linger`. The workflow: re-push the prior repo JSON via `n8n_update_full_workflow`. Remove the forced-command key by setting `memory_worker_ssh_pubkey_value: ""` + `authorized_key state=absent` (or redeploy). Read commands are unaffected throughout.

## Out of scope (tracked)
- Dead-man's switch n8n alert (absence-of-report) + Grafana dashboard.
- MCP `memory_ops` for Claude (Claude calls `memctl`/SSH directly).
- iOS Shortcut transport.
- Pipeline-level improvements (hybrid search, VPAI re-index — note: VPAI is currently excluded from indexing on purpose, see `defaults/main.yml`).
- R9 reconciliation in `deploy-workflow.sh` (the live IF v2 contradicts the rule — flagged to user + memory; not patched here).
