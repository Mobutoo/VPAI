#!/usr/bin/env python3
"""Configure Kitsu project for VideoRef pipeline.

- Associate VideoRef entity type to project
- Create metadata descriptors (style, mood, colors, motion, prompt)
- Create task types (Analysis, Workflow Generation)
- Regenerate bot token
"""
import json
import sys
import urllib.request
import urllib.error

KITSU_URL = "https://boss.ewutelo.cloud"
ADMIN_EMAIL = "seko.mobutoo@gmail.com"
ADMIN_PASSWORD = "Admin2026!"
BOT_EMAIL = "videoref.agent@gmail.com"

PROJECT_ID = "19b9faf4-f7c4-4829-9739-cbf7c3181941"
VIDEOREF_TYPE_ID = "2011f318-ecbd-44ba-9c14-5e18af028d25"


def api(method, path, token, data=None):
    """Make API call to Kitsu/Zou."""
    url = f"{KITSU_URL}/api{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  ERROR {e.code} {method} {path}: {body}")
        return None


def login():
    """Login and get JWT token."""
    body = f"email={ADMIN_EMAIL}&password={ADMIN_PASSWORD}".encode()
    req = urllib.request.Request(
        f"{KITSU_URL}/api/auth/login",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        if not data.get("login"):
            print(f"Login failed: {data}")
            sys.exit(1)
        return data["access_token"]


def main():
    print("=== LOGIN ===")
    token = login()
    print(f"  Logged in as {ADMIN_EMAIL}")

    # 1. Get project info
    print("\n=== PROJECT INFO ===")
    project = api("GET", f"/data/projects/{PROJECT_ID}", token)
    if not project:
        print("  Project not found!")
        sys.exit(1)
    print(f"  Name: {project['name']}")
    print(f"  Type: {project.get('production_type', '?')}")

    # 2. Add VideoRef type to project asset_types
    print("\n=== ADD VIDEOREF TYPE TO PROJECT ===")
    # In Zou, project.asset_types is a list of type IDs in project settings
    # We need to add it via the production settings API
    # Try: POST /data/projects/{id}/settings/asset-types/add
    result = api("POST", f"/data/projects/{PROJECT_ID}/settings/asset-types/add",
                 token, [{"asset_type_id": VIDEOREF_TYPE_ID}])
    if result is None:
        # Alternative: link through entity-links
        # POST /data/projects/{project_id}/asset-types with body
        result = api("POST", f"/data/projects/{PROJECT_ID}/settings/asset-types",
                     token, [VIDEOREF_TYPE_ID])
    if result is None:
        # Try updating project directly to add asset type
        result = api("PUT", f"/data/projects/{PROJECT_ID}", token, {
            "asset_types": [VIDEOREF_TYPE_ID],
        })
    print(f"  Result: {json.dumps(result)[:200] if result else 'FAILED all methods'}")

    # 3. Create metadata descriptors for the project
    print("\n=== METADATA DESCRIPTORS ===")
    # Zou stores custom metadata as "descriptors" on the project
    # They appear as columns in the UI
    descriptors = [
        {"name": "Style", "field_name": "videoref_style", "choices": [], "entity_type": "Asset"},
        {"name": "Mood", "field_name": "videoref_mood", "choices": [], "entity_type": "Asset"},
        {"name": "Colors", "field_name": "videoref_colors", "choices": [], "entity_type": "Asset"},
        {"name": "Motion", "field_name": "videoref_motion", "choices": ["low", "medium", "high"], "entity_type": "Asset"},
        {"name": "AI Prompt", "field_name": "videoref_prompt", "choices": [], "entity_type": "Asset"},
    ]

    # Get existing descriptors
    existing = api("GET", f"/data/projects/{PROJECT_ID}/metadata-descriptors", token)
    existing_names = set()
    if existing and isinstance(existing, list):
        existing_names = {d.get("name") for d in existing}
        print(f"  Existing: {existing_names}")

    for desc in descriptors:
        if desc["name"] in existing_names:
            print(f"  {desc['name']}: already exists")
            continue
        result = api("POST", f"/data/projects/{PROJECT_ID}/metadata-descriptors",
                     token, desc)
        if result:
            print(f"  {desc['name']}: created (id={result.get('id', '?')[:12]})")
        else:
            print(f"  {desc['name']}: FAILED")

    # 4. Create task types for VideoRef workflow
    print("\n=== TASK TYPES ===")
    task_types_needed = [
        {"name": "Analysis", "short_name": "ANL", "color": "#9B59B6",
         "description": "AI video analysis (keyframes, colors, motion, style)"},
        {"name": "Workflow", "short_name": "WKF", "color": "#2ECC71",
         "description": "ComfyUI workflow generation from templates"},
    ]

    # Get existing task types
    existing_tt = api("GET", "/data/task-types", token)
    existing_tt_names = set()
    if existing_tt and isinstance(existing_tt, list):
        existing_tt_names = {t.get("name") for t in existing_tt}
        print(f"  Existing: {existing_tt_names}")

    for tt in task_types_needed:
        if tt["name"] in existing_tt_names:
            print(f"  {tt['name']}: already exists")
            continue
        # Task types are global, created via /data/task-types
        result = api("POST", "/data/task-types", token, tt)
        if result:
            print(f"  {tt['name']}: created (id={result.get('id', '?')[:12]})")
        else:
            print(f"  {tt['name']}: FAILED")

    # 5. Add task types to project settings
    print("\n=== ADD TASK TYPES TO PROJECT ===")
    all_tt = api("GET", "/data/task-types", token)
    tt_map = {t["name"]: t["id"] for t in (all_tt or [])}
    for name in ["Analysis", "Workflow"]:
        if name in tt_map:
            result = api("POST",
                         f"/data/projects/{PROJECT_ID}/settings/asset-task-types",
                         token, [tt_map[name]])
            if result is None:
                # Try alternative
                api("POST",
                    f"/data/projects/{PROJECT_ID}/settings/asset-task-types/add",
                    token, [{"task_type_id": tt_map[name]}])
            print(f"  {name}: added to project settings")

    # 6. Create/refresh bot token
    print("\n=== BOT TOKEN ===")
    bots = api("GET", "/data/persons?is_bot=true", token)
    bot = None
    if bots and isinstance(bots, list):
        bot = next((b for b in bots if b.get("email") == BOT_EMAIL), None)

    if bot:
        print(f"  Bot exists: {bot['first_name']} (id={bot['id'][:12]})")
        # Get bot token
        bot_tokens = api("GET", f"/data/persons/{bot['id']}/api-tokens", token)
        if bot_tokens:
            print(f"  Tokens: {len(bot_tokens)}")
    else:
        print("  Bot not found. Create via CLI: zou create-bot ...")

    # 7. Verify assets visible
    print("\n=== VERIFY ASSETS ===")
    assets = api("GET", f"/data/projects/{PROJECT_ID}/assets", token)
    if assets:
        print(f"  Total assets: {len(assets)}")
        for a in assets:
            print(f"  - {a['name']} | type={a.get('asset_type_name', '?')} | data={list(a.get('data',{}).keys())[:3]}")
    else:
        print("  No assets or error")

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
