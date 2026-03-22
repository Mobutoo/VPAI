#!/usr/bin/env python3
"""Audit Kitsu project state — run inside videoref container."""
import asyncio
import aiohttp
import os
import json

KITSU_URL = os.environ["KITSU_URL"]
KITSU_TOKEN = os.environ["KITSU_TOKEN"]


async def audit():
    h = {"Authorization": f"Bearer {KITSU_TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        # Get latest project
        async with s.get(f"{KITSU_URL}/api/data/projects", headers=h) as r:
            projects = await r.json()
        p = projects[-1]
        pid = p["id"]
        print(f"=== PROJECT: {p['name']} ({pid[:8]}) ===")

        # Sequences
        async with s.get(f"{KITSU_URL}/api/data/projects/{pid}/sequences", headers=h) as r:
            seqs = await r.json()
        print(f"\nSequences: {len(seqs)}")
        for sq in seqs:
            print(f"  - {sq['name']} ({sq['id'][:8]})")

        # Shots
        shots = []
        for sq in seqs:
            async with s.get(f"{KITSU_URL}/api/data/sequences/{sq['id']}/shots", headers=h) as r:
                sshots = await r.json()
            shots.extend(sshots)
        print(f"\nShots: {len(shots)}")
        for sh in shots:
            pf = sh.get("preview_file_id") or "NONE"
            desc = str(sh.get("description", ""))[:60]
            print(f"  - {sh['name']} preview={'YES' if pf != 'NONE' else 'NONE'} desc={desc}")

        # Assets
        async with s.get(f"{KITSU_URL}/api/data/projects/{pid}/assets", headers=h) as r:
            assets = await r.json()
        print(f"\nAssets: {len(assets) if isinstance(assets, list) else 'error'}")
        if isinstance(assets, list):
            for a in assets:
                data = a.get("data", {}) or {}
                print(f"  - {a['name']} type={a.get('asset_type_name','?')} prompt={str(data.get('ai_prompt',''))[:60]}")

        # Concepts
        async with s.get(f"{KITSU_URL}/api/data/projects/{pid}/concepts", headers=h) as r:
            concepts = await r.json()
        print(f"\nConcepts: {len(concepts)}")
        for c in concepts:
            pf = c.get("preview_file_id") or "NONE"
            print(f"  - {c['name']} preview={'YES' if pf != 'NONE' else 'NONE'}")

        # Tasks on first shot
        if shots:
            shot_id = shots[0]["id"]
            async with s.get(f"{KITSU_URL}/api/data/shots/{shot_id}/tasks", headers=h) as r:
                tasks = await r.json()
            print(f"\nTasks on {shots[0]['name']}: {len(tasks)}")
            for t in tasks:
                print(f"  - {t.get('task_type_name','?'):20s} status={t.get('task_status_name','?')}")
                # Get comments
                async with s.get(f"{KITSU_URL}/api/data/tasks/{t['id']}/comments", headers=h) as rc:
                    comments = await rc.json()
                for cm in (comments if isinstance(comments, list) else []):
                    txt = (cm.get("text", "") or "")[:80]
                    previews = cm.get("previews", [])
                    print(f"      comment: previews={len(previews)} text={txt}")


asyncio.run(audit())
