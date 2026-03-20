#!/usr/bin/env python3
"""Fix all _kitsu_api() calls that pass dicts as positional args instead of json_body=."""
import re

APP = "roles/videoref-engine/files/app.py"

with open(APP) as f:
    content = f.read()

# Strategy: find all _kitsu_api calls, check if 4th arg is a bare dict
lines = content.split("\n")
fixed = 0

for i, line in enumerate(lines):
    stripped = line.strip()
    # Look for lines that are just a dict opening as an arg
    if stripped.startswith("{") and "json_body" not in line and "kwargs" not in line:
        # Check context: is this inside a _kitsu_api call?
        # Look back to find the function call
        for j in range(max(0, i-5), i):
            if "_kitsu_api(" in lines[j]:
                # This bare { is a positional dict arg — fix it
                lines[i] = line.replace("{", "json_body={", 1)
                fixed += 1
                break

with open(APP, "w") as f:
    f.write("\n".join(lines))

# Verify syntax
compile("\n".join(lines), APP, "exec")
print(f"Fixed {fixed} positional dict args. Syntax OK.")
