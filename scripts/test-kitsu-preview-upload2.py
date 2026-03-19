#!/usr/bin/env python3
"""Test Kitsu preview upload with urllib (no curl needed)."""
import json
import urllib.request
import urllib.error
import io

KITSU = "http://localhost"
PREVIEW_ID = "bc3595e7-9146-4f71-9719-2ec38f5e61e8"

# Login
data = "email=seko.mobutoo@gmail.com&password=Admin2026!".encode()
req = urllib.request.Request(f"{KITSU}/api/auth/login", data=data, method="POST")
with urllib.request.urlopen(req) as r:
    token = json.loads(r.read())["access_token"]

# Minimal JPEG data
jpeg_data = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9,
])

# Build multipart form data manually
boundary = "----Boundary12345"
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="keyframe.jpg"\r\n'
    f"Content-Type: image/jpeg\r\n\r\n"
).encode() + jpeg_data + f"\r\n--{boundary}--\r\n".encode()

for method in ["PUT", "POST"]:
    for port_label, base in [("Nginx:80", "http://localhost/api"), ("Flask:5000", "http://localhost:5000")]:
        url = f"{base}/pictures/preview-files/{PREVIEW_ID}"
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                print(f"{method} {port_label}: {r.status}")
        except urllib.error.HTTPError as e:
            print(f"{method} {port_label}: {e.code} {e.reason}")
        except Exception as e:
            print(f"{method} {port_label}: {e}")
