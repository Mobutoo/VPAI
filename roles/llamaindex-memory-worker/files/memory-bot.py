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
