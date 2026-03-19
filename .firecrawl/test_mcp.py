import requests
import json

TOKEN = "CbR2XDA3hytjrhudcjY7y7UNiHaxI98ByZs5Wci0WMM="
BASE = "http://100.64.0.1:3001/mcp"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream"
}

def mcp_call(session_id, method, params, req_id):
    h = {**HEADERS}
    if session_id:
        h["Mcp-Session-Id"] = session_id
    r = requests.post(BASE, headers=h, json={
        "jsonrpc": "2.0", "id": req_id,
        "method": method, "params": params
    }, stream=True)
    session = r.headers.get("mcp-session-id")
    data = ""
    for line in r.iter_lines():
        if line:
            line = line.decode() if isinstance(line, bytes) else line
            if line.startswith("data: "):
                data = line[6:]
    return session, json.loads(data) if data else {}

# 1. Init
sid, init_resp = mcp_call(None, "initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "1.0"}
}, 1)
print(f"Session: {sid}")
print(f"Server: {init_resp.get('result', {}).get('serverInfo', {})}")
print()

# 2. Search Telegram nodes
_, resp = mcp_call(sid, "tools/call", {
    "name": "search_nodes",
    "arguments": {"query": "telegram send message", "limit": 5}
}, 2)
results = json.loads(resp["result"]["content"][0]["text"]).get("results", [])
print("=== Telegram nodes ===")
for n in results:
    print(f"  {n.get('nodeType')} - {n.get('displayName')}")
print()

# 3. Search HTTP Request
_, resp = mcp_call(sid, "tools/call", {
    "name": "search_nodes",
    "arguments": {"query": "HTTP request API call", "limit": 3}
}, 3)
results2 = json.loads(resp["result"]["content"][0]["text"]).get("results", [])
print("=== HTTP nodes ===")
for n in results2:
    print(f"  {n.get('nodeType')} - {n.get('displayName')}")
print()

# 4. Get scheduleTrigger schema
_, resp = mcp_call(sid, "tools/call", {
    "name": "get_node",
    "arguments": {"nodeType": "nodes-base.scheduleTrigger", "mode": "essential"}
}, 4)
info = json.loads(resp["result"]["content"][0]["text"])
print("=== scheduleTrigger ===")
print(f"  displayName: {info.get('displayName')}")
print(f"  description: {info.get('description')}")
props = info.get("properties", [])
for p in props[:4]:
    print(f"  prop: {p.get('name')} ({p.get('type')}) - {p.get('displayName')}")
print()

# 5. Get Telegram schema
_, resp = mcp_call(sid, "tools/call", {
    "name": "get_node",
    "arguments": {"nodeType": "nodes-base.telegram", "mode": "essential"}
}, 5)
info2 = json.loads(resp["result"]["content"][0]["text"])
print("=== Telegram node ===")
print(f"  displayName: {info2.get('displayName')}")
print(f"  description: {info2.get('description')}")
props2 = info2.get("properties", [])
for p in props2[:5]:
    print(f"  prop: {p.get('name')} ({p.get('type')}) - {p.get('displayName')}")
