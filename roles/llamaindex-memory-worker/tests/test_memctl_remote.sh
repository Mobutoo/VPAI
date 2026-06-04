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

# valid action -> memctl run
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="run" bash "$WRAP" >/dev/null 2>&1
ok "$([ "$(called)" = "MEMCTL_CALLED:run" ] && echo 1)" "valid 'run' dispatches memctl run"

# injection with glued ';' -> DENIED (awk \$1 = 'status;' -> no case match), memctl NOT called
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="status; rm -rf /" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -ne 0 ] && echo 1)" "'status; rm' denied (glued ;), memctl not called"

# space before ';' -> \$1='status' -> runs status, drops the rest (rm never runs)
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="status ; rm -rf /" bash "$WRAP" >/dev/null 2>&1
ok "$([ "$(called)" = "MEMCTL_CALLED:status" ] && echo 1)" "'status ; rm' runs only status"

# multiline -> denied
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="$(printf 'status\nrm -rf /')" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -ne 0 ] && echo 1)" "multiline input denied"

# unknown command -> denied, exit 2
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="evil" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -eq 2 ] && echo 1)" "unknown command denied exit 2"

# empty -> denied
rm -f "$TMP/called"; SSH_ORIGINAL_COMMAND="" bash "$WRAP" >/dev/null 2>&1; rc=$?
ok "$([ "$(called)" = "NONE" ] && [ $rc -ne 0 ] && echo 1)" "empty command denied"

rm -rf "$TMP"; [ "$fail" = 0 ] && echo "test_memctl_remote PASS" || { echo "test_memctl_remote FAIL"; exit 1; }
