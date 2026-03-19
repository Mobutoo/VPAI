import requests, json, time

TOKEN = "CbR2XDA3hytjrhudcjY7y7UNiHaxI98ByZs5Wci0WMM="
BASE = "http://100.64.0.1:3001/mcp"

def call(sid, method, params, req_id):
    h = {
        "Authorization": "Bearer " + TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    if sid:
        h["Mcp-Session-Id"] = sid
    r = requests.post(BASE, headers=h,
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        stream=True, timeout=20)
    sid2 = r.headers.get("mcp-session-id") or sid
    rem = r.headers.get("RateLimit-Remaining", "?")
    data_events = []
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            data_events.append(line[6:])
    parsed = {}
    for d in data_events:
        d = d.strip()
        if d and d != "[DONE]":
            try:
                parsed = json.loads(d)
                break
            except Exception:
                pass
    return sid2, parsed, r.status_code, rem

# 1. init
sid, resp, code, rem = call(None, "initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "1.0"}
}, 1)
print(f"1. init: HTTP {code}, rate_remaining={rem}")
print(f"   session: {sid}")
print(f"   server: {resp.get('result', {}).get('serverInfo', {})}")

if code == 429:
    print("Rate limited — wait and retry")
    exit(1)

time.sleep(0.5)

# 2. search telegram
sid, resp, code, rem = call(sid, "tools/call", {
    "name": "search_nodes",
    "arguments": {"query": "telegram", "limit": 4}
}, 2)
print(f"\n2. search 'telegram': HTTP {code}, rate_remaining={rem}")
if code == 200 and "result" in resp:
    inner = json.loads(resp["result"]["content"][0]["text"])
    for n in inner.get("results", []):
        print(f"   {n.get('nodeType')} - {n.get('displayName')}")

time.sleep(0.5)

# 3. get_node Telegram (minimal)
sid, resp, code, rem = call(sid, "tools/call", {
    "name": "get_node",
    "arguments": {"nodeType": "nodes-base.telegram", "mode": "minimal"}
}, 3)
print(f"\n3. get_node telegram: HTTP {code}, rate_remaining={rem}")
if code == 200 and "result" in resp:
    text = resp["result"]["content"][0]["text"]
    info = json.loads(text)
    print(f"   Name: {info.get('displayName')}")
    print(f"   Description: {info.get('description')}")
    print(f"   Version: {info.get('version')}")

time.sleep(0.5)

# 4. validate a real workflow
print("\n4. validate_workflow (Schedule→HTTP→Telegram)")
workflow = {
    "name": "Budget Alert Telegram",
    "nodes": [
        {
            "id": "n1", "name": "Every Hour",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2, "position": [0, 0],
            "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}}
        },
        {
            "id": "n2", "name": "Check LiteLLM Budget",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": [250, 0],
            "parameters": {
                "method": "GET",
                "url": "http://litellm:4000/spend/logs",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth"
            }
        },
        {
            "id": "n3", "name": "Send Telegram Alert",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2, "position": [500, 0],
            "parameters": {
                "chatId": "={{ $vars.TELEGRAM_CHAT_ID }}",
                "text": "=\ud83d\udcb0 LiteLLM Budget: {{ $json.spend }}$ / 5$"
            }
        }
    ],
    "connections": {
        "Every Hour": {"main": [[{"node": "Check LiteLLM Budget", "type": "main", "index": 0}]]},
        "Check LiteLLM Budget": {"main": [[{"node": "Send Telegram Alert", "type": "main", "index": 0}]]}
    }
}
sid, resp, code, rem = call(sid, "tools/call", {
    "name": "validate_workflow",
    "arguments": {"workflow": workflow}
}, 4)
print(f"   HTTP {code}, rate_remaining={rem}")
if code == 200 and "result" in resp:
    text = resp["result"]["content"][0]["text"]
    result = json.loads(text)
    print(f"   Valid: {result.get('valid')}")
    for e in result.get("errors", []):
        print(f"   ERROR: {e}")
    for w in result.get("warnings", []):
        print(f"   WARN:  {w}")
    for s in result.get("suggestions", [])[:3]:
        print(f"   SUGG:  {s}")
elif code == 429:
    print("   429 Rate limited")
