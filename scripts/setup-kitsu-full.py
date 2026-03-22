#!/usr/bin/env python3
"""Full Kitsu configuration for VideoRef pipeline.

Based on official documentation (kitsu.cg-wire.com + dev.kitsu.cloud):
1. Global Library: Departments, Task Statuses
2. Production settings: Asset types, Task types, Metadata descriptors
3. Bot token refresh
4. Team assignment
"""
import json
import sys
import urllib.request
import urllib.error

KITSU_URL = "https://boss.ewutelo.cloud"
ADMIN_EMAIL = "seko.mobutoo@gmail.com"
ADMIN_PASSWORD = "Admin2026!"


def api(method, path, token, data=None):
    url = f"{KITSU_URL}/api{path}"
    body = json.dumps(data).encode() if data else None
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            if not content or not content.strip():
                return {"_ok": True}
            return json.loads(content)
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:200]
        return {"_error": True, "_status": e.code, "_body": err}


def login():
    body = f"email={ADMIN_EMAIL}&password={ADMIN_PASSWORD}".encode()
    req = urllib.request.Request(f"{KITSU_URL}/api/auth/login", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        if not data.get("login"):
            print(f"Login failed: {data}")
            sys.exit(1)
        return data["access_token"]


def find_or_create(token, path, name, extra=None):
    """Find entity by name or create it."""
    items = api("GET", path, token)
    if isinstance(items, list):
        match = next((i for i in items if i.get("name") == name), None)
        if match:
            return match, False
    payload = {"name": name}
    if extra:
        payload.update(extra)
    result = api("POST", path, token, payload)
    if result and not result.get("_error"):
        return result, True
    return result, False


def main():
    token = login()
    print(f"Logged in as {ADMIN_EMAIL}\n")

    PROJECT_ID = "19b9faf4-f7c4-4829-9739-cbf7c3181941"

    # ================================================================
    # 1. DEPARTMENTS (Global Library)
    # ================================================================
    print("=" * 60)
    print("1. DEPARTMENTS")
    print("=" * 60)
    departments = [
        {"name": "AI", "color": "#9B59B6"},
        {"name": "Animation", "color": "#3498DB"},
        {"name": "Compositing", "color": "#E67E22"},
        {"name": "Direction", "color": "#E74C3C"},
    ]
    dept_ids = {}
    for dept in departments:
        result, created = find_or_create(token, "/data/departments", dept["name"], {"color": dept["color"]})
        status = "CREATED" if created else "exists"
        dept_id = result.get("id", "?")
        dept_ids[dept["name"]] = dept_id
        print(f"  {dept['name']}: {status} (id={dept_id[:12]})")

    # ================================================================
    # 2. TASK STATUSES (Global Library)
    # ================================================================
    print(f"\n{'=' * 60}")
    print("2. TASK STATUSES")
    print("=" * 60)
    statuses = [
        {"name": "Queued", "short_name": "QUE", "color": "#95A5A6",
         "is_default": False, "is_done": False, "is_retake": False},
        {"name": "Processing", "short_name": "PROC", "color": "#F39C12",
         "is_default": False, "is_done": False, "is_retake": False},
        {"name": "Completed", "short_name": "COMP", "color": "#27AE60",
         "is_default": False, "is_done": True, "is_retake": False},
        {"name": "Failed", "short_name": "FAIL", "color": "#E74C3C",
         "is_default": False, "is_done": False, "is_retake": True},
    ]
    status_ids = {}
    for s in statuses:
        result, created = find_or_create(
            token, "/data/task-status", s["name"],
            {k: v for k, v in s.items() if k != "name"}
        )
        status = "CREATED" if created else "exists"
        sid = result.get("id", "?")
        status_ids[s["name"]] = sid
        print(f"  {s['name']} ({s['short_name']}): {status} (id={sid[:12]})")

    # ================================================================
    # 3. TASK TYPES — link to AI department
    # ================================================================
    print(f"\n{'=' * 60}")
    print("3. TASK TYPES")
    print("=" * 60)
    task_types = [
        {"name": "Analysis", "short_name": "ANL", "color": "#9B59B6",
         "for_entity": "Asset", "department_id": dept_ids.get("AI", "")},
        {"name": "Workflow", "short_name": "WKF", "color": "#2ECC71",
         "for_entity": "Asset", "department_id": dept_ids.get("AI", "")},
    ]
    tt_ids = {}
    for tt in task_types:
        result, created = find_or_create(
            token, "/data/task-types", tt["name"],
            {k: v for k, v in tt.items() if k != "name"}
        )
        if not created and result and not result.get("_error"):
            # Update department_id if not set
            if tt.get("department_id") and not result.get("department_id"):
                api("PUT", f"/data/task-types/{result['id']}", token,
                    {"department_id": tt["department_id"]})
                print(f"  {tt['name']}: exists, updated department -> AI")
            else:
                print(f"  {tt['name']}: exists (id={result.get('id', '?')[:12]})")
        else:
            print(f"  {tt['name']}: {'CREATED' if created else 'ERROR'} (id={result.get('id', '?')[:12]})")
        tt_ids[tt["name"]] = result.get("id", "")

    # ================================================================
    # 4. ASSET TYPE "VideoRef" — already exists, get ID
    # ================================================================
    print(f"\n{'=' * 60}")
    print("4. ASSET TYPE VideoRef")
    print("=" * 60)
    entity_types = api("GET", "/data/entity-types", token)
    vref_type = next((t for t in entity_types if t["name"] == "VideoRef"), None)
    if vref_type:
        print(f"  VideoRef: exists (id={vref_type['id'][:12]})")
    else:
        vref_type = api("POST", "/data/entity-types", token, {"name": "VideoRef"})
        print(f"  VideoRef: CREATED (id={vref_type['id'][:12]})")

    # ================================================================
    # 5. METADATA DESCRIPTORS (Project-level)
    # ================================================================
    print(f"\n{'=' * 60}")
    print("5. METADATA DESCRIPTORS")
    print("=" * 60)
    # Delete existing ones and recreate properly
    existing = api("GET", f"/data/projects/{PROJECT_ID}/metadata-descriptors", token)
    if isinstance(existing, list):
        for d in existing:
            api("DELETE", f"/data/projects/{PROJECT_ID}/metadata-descriptors/{d['id']}", token)
            print(f"  Deleted old: {d['name']}")

    descriptors = [
        {"name": "Style", "field_name": "style", "data_type": "string", "entity_type": "Asset"},
        {"name": "Mood", "field_name": "mood", "data_type": "string", "entity_type": "Asset"},
        {"name": "Colors", "field_name": "colors", "data_type": "string", "entity_type": "Asset"},
        {"name": "Motion", "field_name": "motion", "data_type": "list",
         "choices": ["low", "medium", "high"], "entity_type": "Asset"},
        {"name": "AI Prompt", "field_name": "ai_prompt", "data_type": "string", "entity_type": "Asset"},
    ]
    for desc in descriptors:
        result = api("POST", f"/data/projects/{PROJECT_ID}/metadata-descriptors", token, desc)
        if result and not result.get("_error"):
            print(f"  {desc['name']}: CREATED ({desc['data_type']}) field={result.get('field_name', '?')}")
        else:
            print(f"  {desc['name']}: ERROR {result}")

    # ================================================================
    # 6. UPDATE EXISTING ASSETS — align field names with descriptors
    # ================================================================
    print(f"\n{'=' * 60}")
    print("6. FIX ASSET DATA FIELDS")
    print("=" * 60)
    assets = api("GET", f"/data/projects/{PROJECT_ID}/assets", token)
    if isinstance(assets, list):
        for a in assets:
            data = a.get("data") or {}
            desc = a.get("description") or ""
            new_data = {}

            # Parse from existing data (with prefix mapping)
            mapping = {
                "videoref_style": "style", "videoref_mood": "mood",
                "videoref_colors": "colors", "videoref_motion": "motion",
                "videoref_prompt": "ai_prompt",
                "style": "style", "mood": "mood", "colors": "colors",
                "motion": "motion", "ai_prompt": "ai_prompt",
            }
            for old_key, new_key in mapping.items():
                if old_key in data and data[old_key]:
                    new_data[new_key] = data[old_key]

            # Fallback: parse from description
            for line in desc.split("\n"):
                if line.startswith("Style: ") and "style" not in new_data:
                    new_data["style"] = line[7:].strip()
                elif line.startswith("Mood: ") and "mood" not in new_data:
                    new_data["mood"] = line[6:].strip()
                elif line.startswith("Colors: ") and "colors" not in new_data:
                    new_data["colors"] = line[8:].strip()
                elif line.startswith("Motion: ") and "motion" not in new_data:
                    new_data["motion"] = line[8:].strip()
                elif line.startswith("Prompt: ") and "ai_prompt" not in new_data:
                    new_data["ai_prompt"] = line[8:].strip()

            if new_data:
                result = api("PUT", f"/data/entities/{a['id']}", token, {"data": new_data})
                if result and not result.get("_error"):
                    print(f"  {a['name']}: updated {list(new_data.keys())}")
                else:
                    print(f"  {a['name']}: ERROR {result}")
            else:
                print(f"  {a['name']}: no data to update")

    # ================================================================
    # 7. BOT — refresh token
    # ================================================================
    print(f"\n{'=' * 60}")
    print("7. BOT TOKEN")
    print("=" * 60)
    persons = api("GET", "/data/persons", token)
    if isinstance(persons, list):
        bot = next((p for p in persons if p.get("is_bot")), None)
        if bot:
            print(f"  Bot: {bot.get('first_name', '?')} (id={bot['id'][:12]})")
            print(f"  Email: {bot.get('email', '?')}")
            print(f"  Role: {bot.get('role', '?')}")
            # Note: bot JWT token was generated at creation
            # To regenerate: use Kitsu UI or zou CLI
        else:
            print("  No bot found. Will need to create via CLI.")

    # ================================================================
    # 8. STATUS AUTOMATION (optional — auto-complete Analysis → Workflow)
    # ================================================================
    print(f"\n{'=' * 60}")
    print("8. STATUS AUTOMATION")
    print("=" * 60)
    # When Analysis task is "Completed", set Workflow task to "Queued"
    if tt_ids.get("Analysis") and tt_ids.get("Workflow"):
        if status_ids.get("Completed") and status_ids.get("Queued"):
            automation = {
                "entity_type": "asset",
                "in_task_type_id": tt_ids["Analysis"],
                "in_task_status_id": status_ids["Completed"],
                "out_field_type": "status",
                "out_task_type_id": tt_ids["Workflow"],
                "out_task_status_id": status_ids["Queued"],
            }
            result = api("POST", f"/data/projects/{PROJECT_ID}/status-automations",
                         token, automation)
            if result and not result.get("_error"):
                print(f"  Analysis[Completed] → Workflow[Queued]: CREATED")
            else:
                print(f"  Automation: {result}")
        else:
            print("  Missing status IDs, skipping automation")
    else:
        print("  Missing task type IDs, skipping automation")

    # ================================================================
    # 9. FINAL VERIFICATION
    # ================================================================
    print(f"\n{'=' * 60}")
    print("9. VERIFICATION")
    print("=" * 60)

    descs = api("GET", f"/data/projects/{PROJECT_ID}/metadata-descriptors", token)
    if isinstance(descs, list):
        print(f"  Metadata descriptors: {len(descs)}")
        for d in descs:
            print(f"    {d['name']} ({d['data_type']}) -> field={d['field_name']}")

    assets = api("GET", f"/data/projects/{PROJECT_ID}/assets", token)
    if isinstance(assets, list):
        print(f"\n  Assets: {len(assets)}")
        for a in assets:
            data = a.get("data") or {}
            print(f"    {a['name']}: {list(data.keys())}")

    print("\n  Done! Open https://boss.ewutelo.cloud to verify in the UI.")
    print("  Login: seko.mobutoo@gmail.com / Admin2026!")


if __name__ == "__main__":
    main()
