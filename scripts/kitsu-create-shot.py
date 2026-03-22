#!/usr/bin/env python3
"""Create shots directly in Kitsu PostgreSQL.

Workaround for Zou 1.0.18 where POST /data/projects/{id}/shots returns 404.
"""
import json
import subprocess
import uuid
import urllib.request


PROJECT_ID = "19b9faf4-f7c4-4829-9739-cbf7c3181941"
SEQ_ID = "edb8375a-0e5e-4ed3-9e90-59f6e63cf3e9"
SHOT_TYPE_ID = "7a1b7c9e-74eb-40a3-95fe-ce0f6967a989"


def sql(query):
    escaped = query.replace('"', '\\"')
    r = subprocess.run(
        ["su", "-", "postgres", "-c", 'psql zoudb -t -A -c "' + escaped + '"'],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def create_shot(name, data_dict):
    shot_id = str(uuid.uuid4())
    data_json = json.dumps(data_dict).replace("'", "''")
    result = sql(
        "INSERT INTO entity (id, name, project_id, entity_type_id, parent_id, "
        "data, status, created_at, updated_at) VALUES ("
        f"'{shot_id}', '{name}', '{PROJECT_ID}', '{SHOT_TYPE_ID}', '{SEQ_ID}', "
        f"'{data_json}'::jsonb, 'running', now(), now()) "
        "RETURNING id"
    )
    return result.strip() if result else None


def main():
    # Create test shot
    shot_id = create_shot("SH0010", {
        "style": "3D Animation",
        "mood": "Playful",
        "colors": "#d1c8b4, #3b312e",
        "motion": "low",
        "ai_prompt": "A playful 3D animated scene with colorful characters",
    })
    print(f"Shot SH0010 created: {shot_id}")

    # Verify via API
    data = "email=seko.mobutoo@gmail.com&password=Admin2026!".encode()
    req = urllib.request.Request(
        "http://localhost/api/auth/login", data=data, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        token = json.loads(r.read())["access_token"]

    req2 = urllib.request.Request(
        f"http://localhost/api/data/projects/{PROJECT_ID}/shots",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req2) as r2:
        shots = json.loads(r2.read())
        print(f"API: {len(shots)} shots visible")
        for s in shots:
            print(f"  {s['name']} data={list((s.get('data') or {}).keys())}")


if __name__ == "__main__":
    main()
