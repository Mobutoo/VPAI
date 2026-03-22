#!/usr/bin/env python3
"""Check if a Qdrant collection exists, create it if not."""
import json
import sys
import urllib.request
import urllib.error

QDRANT_URL = "http://qdrant:6333"
QDRANT_KEY = sys.argv[1] if len(sys.argv) > 1 else ""
COLLECTION = sys.argv[2] if len(sys.argv) > 2 else "vpai_rex"

headers = {"api-key": QDRANT_KEY, "Content-Type": "application/json"}


def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{QDRANT_URL}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()[:200]}


# Check collection
result = api("GET", f"/collections/{COLLECTION}")
if "error" in result:
    print(f"Collection {COLLECTION} not found ({result}). Creating...")
    create_result = api("PUT", f"/collections/{COLLECTION}", {
        "vectors": {
            "size": 1536,
            "distance": "Cosine",
        },
    })
    print(f"Create result: {json.dumps(create_result, indent=2)}")
else:
    info = result.get("result", {})
    points = info.get("points_count", "?")
    status = info.get("status", "?")
    print(f"Collection {COLLECTION}: status={status}, points={points}")
