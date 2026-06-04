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
