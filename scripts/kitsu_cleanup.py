#!/usr/bin/env python3
"""Kitsu cleanup: migrate assets to Asset Library, then delete other projects.

Usage:
    KITSU_URL=http://... KITSU_TOKEN=... python3 kitsu_cleanup.py [--dry-run]
"""
import argparse
import os
import sys

import requests

KITSU_URL = os.environ.get("KITSU_URL", "")
KITSU_TOKEN = os.environ.get("KITSU_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {KITSU_TOKEN}", "Content-Type": "application/json"}


def api(method: str, path: str, json_body: dict | None = None):
    url = f"{KITSU_URL}/api{path}"
    resp = requests.request(method, url, headers=HEADERS, json=json_body, timeout=30)
    if resp.status_code not in (200, 201, 204):
        print(f"  ERROR {method} {path}: {resp.status_code} {resp.text[:200]}")
        return None
    return resp.json() if resp.text.strip() else None


def main():
    parser = argparse.ArgumentParser(description="Kitsu cleanup: migrate assets then delete projects")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    args = parser.parse_args()

    if not KITSU_URL or not KITSU_TOKEN:
        print("ERROR: KITSU_URL and KITSU_TOKEN env vars required")
        sys.exit(1)

    # List all projects
    projects = api("GET", "/data/projects") or []
    print(f"Found {len(projects)} projects\n")

    # Find Asset Library
    library = next((p for p in projects if p.get("production_type") == "assets"), None)
    if not library:
        print("No Asset Library found (production_type=assets). Creating one...")
        if not args.dry_run:
            library = api("POST", "/data/projects", {
                "name": "Asset Library",
                "production_type": "assets",
            })
        else:
            print("  [DRY-RUN] Would create Asset Library")
            library = {"id": "dry-run-id", "name": "Asset Library"}

    library_id = library["id"]
    print(f"Asset Library: {library['name']} (id={library_id})")

    # Get existing library assets for dedup
    library_assets = api("GET", f"/data/projects/{library_id}/assets") or []
    library_names = {a["name"] for a in library_assets}
    print(f"  Existing library assets: {len(library_names)}\n")

    # Process other projects
    to_delete = [p for p in projects if p["id"] != library_id]
    migrated = 0
    skipped_dup = 0

    for proj in to_delete:
        print(f"Project: {proj['name']} (type={proj.get('production_type', '?')}, id={proj['id']})")
        assets = api("GET", f"/data/projects/{proj['id']}/assets") or []

        for asset in assets:
            name = asset["name"]
            if name in library_names:
                print(f"  SKIP (duplicate): {name}")
                skipped_dup += 1
                continue

            print(f"  MIGRATE: {name} → Asset Library")
            if not args.dry_run:
                api("PUT", f"/data/assets/{asset['id']}", {"project_id": library_id})
            library_names.add(name)
            migrated += 1

        print(f"  DELETE project: {proj['name']}")
        if not args.dry_run:
            api("DELETE", f"/data/projects/{proj['id']}")
        print()

    print("=" * 40)
    print(f"Projects deleted: {len(to_delete)}")
    print(f"Assets migrated: {migrated}")
    print(f"Duplicates skipped: {skipped_dup}")
    if args.dry_run:
        print("\n[DRY-RUN] No changes made. Remove --dry-run to execute.")


if __name__ == "__main__":
    main()
