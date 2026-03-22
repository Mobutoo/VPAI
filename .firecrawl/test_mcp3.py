import requests
import json
import time

TOKEN = "CbR2XDA3hytjrhudcjY7y7UNiHaxI98ByZs5Wci0WMM="
BASE = "http://100.64.0.1:3001/mcp"

def mcp_call(session_id, method, params, req_id, debug=False):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    r = requests.post(BASE, headers=headers, json={
        "jsonrpc": "2.0", "id": req_id,
        "method": method, "params": params
    }, stream=True, timeout=20)

    session = r.headers.get("mcp-session-id", session_id)
    rate_remaining = r.headers.get("RateLimit-Remaining", "?")

    if debug:
        print(f"  HTTP {r.status_code}, rate_remaining={rate_remaining}")

    all_lines = []
    data_events = []
    for raw_line in r.iter_lines(decode_unicode=True):
        all_lines.append(raw_line)
        if raw_line.startswith("data: "):
            data_events.append(raw_line[6:])

    if debug:
        print(f"  SSE lines: {len(all_lines)}, data events: {len(data_events)}")
        for i, d in enumerate(data_events):
            print(f"  event[{i}]: {repr(d[:150])}")

    # Try each data event as independent JSON
    for d in data_events:
        d = d.strip()
        if d and d != "[DONE]":
            try:
                return session, json.loads(d)
            except:
                pass
    return session, {}

# Init
print("=== Initialize ===")
sid, resp = mcp_call(None, "initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "1.0"}
}, 1, debug=True)
print(f"Session: {sid}")
print(f"Server: {resp.get('result', {}).get('serverInfo', {})}")
print()

time.sleep(0.5)

# Search telegram (works)
print("=== Search 'telegram send' ===")
_, resp = mcp_call(sid, "tools/call", {
    "name": "search_nodes",
    "arguments": {"query": "telegram send", "limit": 3}
}, 2, debug=True)
if "result" in resp:
    inner = json.loads(resp["result"]["content"][0]["text"])
    for n in inner.get("results", []):
        print(f"  FOUND: {n.get('nodeType')} - {n.get('displayName')}")
print()

time.sleep(0.5)

# get_node with debug
print("=== get_node telegram (debug) ===")
mcp_call(sid, "tools/call", {
    "name": "get_node",
    "arguments": {"nodeType": "nodes-base.telegram", "mode": "minimal"}
}, 3, debug=True)
