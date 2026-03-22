#!/usr/bin/env python3
"""Test Kitsu preview file upload — find the correct method."""
import json
import urllib.request
import urllib.error

KITSU = "http://localhost"
EMAIL = "seko.mobutoo@gmail.com"
PASSWORD = "Admin2026!"

# Login
data = f"email={EMAIL}&password={PASSWORD}".encode()
req = urllib.request.Request(f"{KITSU}/api/auth/login", data=data, method="POST")
with urllib.request.urlopen(req) as r:
    token = json.loads(r.read())["access_token"]
print(f"Logged in")

# Get a preview file ID from existing comments
proj = "19b9faf4-f7c4-4829-9739-cbf7c3181941"
req = urllib.request.Request(
    f"{KITSU}/api/data/projects/{proj}/tasks",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as r:
    tasks = json.loads(r.read())

print(f"Tasks: {len(tasks)}")
if not tasks:
    print("No tasks, cannot test preview upload")
    exit(0)

task_id = tasks[0]["id"]
print(f"Task: {task_id}")

# Get comments on this task
req = urllib.request.Request(
    f"{KITSU}/api/data/tasks/{task_id}/comments",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as r:
    comments = json.loads(r.read())

print(f"Comments: {len(comments)}")
if comments:
    comment = comments[0]
    print(f"Comment: {comment['id']}")
    previews = comment.get("previews", [])
    print(f"Previews on comment: {previews}")

    if previews:
        pid = previews[0]["id"]
        print(f"Preview ID: {pid}")

        # Create test image
        with open("/tmp/test_upload.jpg", "wb") as f:
            # Minimal valid JPEG
            f.write(bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
                0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9,
            ]))

        # Try multiple methods
        import subprocess

        for method in ["PUT", "POST"]:
            print(f"\n=== {method} /pictures/preview-files/{pid[:12]}... ===")
            # Via Nginx (port 80)
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "-X", method,
                 f"{KITSU}/api/pictures/preview-files/{pid}",
                 "-H", f"Authorization: Bearer {token}",
                 "-F", "file=@/tmp/test_upload.jpg"],
                capture_output=True, text=True,
            )
            print(f"  Nginx (port 80): HTTP {result.stdout}")

            # Direct Flask (port 5000)
            result2 = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "-X", method,
                 f"http://localhost:5000/pictures/preview-files/{pid}",
                 "-H", f"Authorization: Bearer {token}",
                 "-F", "file=@/tmp/test_upload.jpg"],
                capture_output=True, text=True,
            )
            print(f"  Flask (port 5000): HTTP {result2.stdout}")
