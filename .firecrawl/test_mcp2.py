import requests
import json
import time

TOKEN = "CbR2XDA3hytjrhudcjY7y7UNiHaxI98ByZs5Wci0WMM="
BASE = "http://100.64.0.1:3001/mcp"

def mcp_call(session_id, method, params, req_id):
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
    }, stream=True, timeout=15)
    # Get full session ID from header
    session = r.headers.get("mcp-session-id", session_id)
    # Parse SSE stream
    data_lines = []
    for raw_line in r.iter_lines(decode_unicode=True):
        if raw_line.startswith("data: "):
            data_lines.append(raw_line[6:])
    # Join all data lines (some responses are multi-line SSE)
    data = "".join(data_lines)
    try:
        return session, json.loads(data)
    except Exception as e:
        print(f"  [parse error] method={method} data_len={len(data)} err={e}")
        print(f"  raw data: {repr(data[:200])}")
        return session, {}

# 1. Init
print("=== 1. Initialize ===")
sid, resp = mcp_call(None, "initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test-claude", "version": "1.0"}
}, 1)
print(f"Session ID: {sid}")
server = resp.get("result", {}).get("serverInfo", {})
print(f"Server: {server}")
print()

# 2. Search Telegram
print("=== 2. Search 'telegram' ===")
_, resp = mcp_call(sid, "tools/call", {
    "name": "search_nodes",
    "arguments": {"query": "telegram", "limit": 3}
}, 2)
if "result" in resp:
    inner = json.loads(resp["result"]["content"][0]["text"])
    for n in inner.get("results", []):
        print(f"  {n.get('nodeType')} - {n.get('displayName')}")
print()

time.sleep(1)

# 3. Get Telegram node properties
print("=== 3. Get Telegram node ===")
_, resp = mcp_call(sid, "tools/call", {
    "name": "get_node",
    "arguments": {"nodeType": "nodes-base.telegram", "mode": "essential"}
}, 3)
if "result" in resp:
    info = json.loads(resp["result"]["content"][0]["text"])
    print(f"  Name: {info.get('displayName')} v{info.get('version')}")
    print(f"  Description: {info.get('description')}")
    print("  Operations:")
    for p in info.get("properties", []):
        if p.get("name") in ("resource", "operation"):
            opts = p.get("options", [])
            print(f"    {p.get('name')}: {[o.get('value') for o in opts[:8]]}")
elif "error" in resp:
    print(f"  Error: {resp['error']}")
print()

time.sleep(1)

# 4. Validate a simple workflow
print("=== 4. Validate workflow (Schedule → HTTP Request → Telegram) ===")
workflow = {
    "name": "Budget Alert",
    "nodes": [
        {
            "id": "node1",
            "name": "Every Hour",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0],
            "parameters": {
                "rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}
            }
        },
        {
            "id": "node2",
            "name": "Get Budget",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [250, 0],
            "parameters": {
                "method": "GET",
                "url": "http://litellm:4000/spend/logs",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth"
            }
        },
        {
            "id": "node3",
            "name": "Alert Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [500, 0],
            "parameters": {
                "chatId": "={{ $vars.TELEGRAM_CHAT_ID }}",
                "text": "=💰 Budget: {{ $json.spend }}$ / 5$"
            }
        }
    ],
    "connections": {
        "Every Hour": {"main": [[{"node": "Get Budget", "type": "main", "index": 0}]]},
        "Get Budget": {"main": [[{"node": "Alert Telegram", "type": "main", "index": 0}]]}
    }
}
_, resp = mcp_call(sid, "tools/call", {
    "name": "validate_workflow",
    "arguments": {"workflow": workflow}
}, 4)
if "result" in resp:
    result_text = resp["result"]["content"][0]["text"]
    result_data = json.loads(result_text)
    print(f"  Valid: {result_data.get('valid')}")
    errors = result_data.get("errors", [])
    warnings = result_data.get("warnings", [])
    suggestions = result_data.get("suggestions", [])
    if errors:
        print(f"  Errors ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")
    if warnings:
        print(f"  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    if suggestions:
        print(f"  Suggestions ({len(suggestions)}):")
        for s in suggestions:
            print(f"    - {s}")
elif "error" in resp:
    print(f"  Error: {resp['error']}")
