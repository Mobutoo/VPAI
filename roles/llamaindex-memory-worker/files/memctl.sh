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
    if [ -n "$r" ]; then qpts="$(printf '%s' "$r" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("result",{}); v=r.get("points_count"); print(v if v is not None else "null")' 2>/dev/null || echo null)"; [ "$qpts" != null ] && qok=true; fi
  fi
  printf '{"last_run_ts":"%s","age_seconds":%s,"spool_depth":%s,"lock_pid":"%s","lock_alive":%s,"state_entries":%s,"qdrant_points":%s,"qdrant_reachable":%s,"timer_enabled":"%s","timer_active":"%s"}\n' \
    "$last_ts" "${age}" "${spool:-0}" "$lp" "$alive" "${state_n:-0}" "${qpts}" "$qok" "$ten" "$tac"
}

cmd_start() { _uctl enable --now "$TIMER" && echo "OK: timer enabled+started"; }
cmd_stop()  { _uctl disable --now "$TIMER" && echo "OK: timer disabled"; }
# --no-block: the worker is Type=oneshot, so `systemctl start` WITHOUT it blocks
# until the whole index run finishes (minutes). That would hang the SSH/webhook
# caller → Telegram retries → duplicate runs. Fire-and-return instead.
cmd_run()   { _uctl start --no-block "$SERVICE" && echo "OK: one-shot run launched"; }
cmd_fix() {
  local lp removed=no; lp="$(_lock_pid)"
  if [ -n "$lp" ] && ! _pid_alive "$lp"; then rm -f "$LOCK" && removed=yes; fi
  _uctl start --no-block "$SERVICE" >/dev/null 2>&1 || true
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
