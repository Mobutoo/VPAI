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
# Reject multiline input immediately — awk NR==1 silently drops line 2+, which
# would allow injection via newline. Explicit pre-check makes the denial visible.
case "$cmd" in *$'\n'*) echo "denied: multiline not allowed" >&2; exit 2 ;; esac
# First token of the first line only — any separator (;, &&, |, newline) glued to
# the token or on later lines fails the case match → denied.
cmd="$(printf '%s' "$cmd" | tr -d '\r' | awk 'NR==1{print $1}')"
case "$cmd" in
  status|start|stop|run|fix) exec bash "$MEMCTL_BIN" "$cmd" ;;
  *) echo "denied: '$cmd' not in {status,start,stop,run,fix}" >&2; exit 2 ;;
esac
