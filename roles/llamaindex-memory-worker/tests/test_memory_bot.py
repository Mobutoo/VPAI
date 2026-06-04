#!/usr/bin/env python3
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

# REGRESSION: whitespace-only text must not raise IndexError
calls.clear(); replies.clear()
try:
    mb.handle_update(upd("   "), owner_chat_id=OWNER)
    check("whitespace-only text: no exception", True)
except IndexError:
    check("whitespace-only text: no exception", False)
check("whitespace-only text: no memctl dispatch", calls == [])

print("test_memory_bot PASS" if fails == 0 else "test_memory_bot FAIL"); sys.exit(fails)
