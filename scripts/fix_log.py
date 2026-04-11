#!/usr/bin/env python3
"""Fix the broken regex in log.py"""
import os

path = "/home/mobuone/jarvis/bridge/log.py"
with open(path, "r") as f:
    content = f.read()

old = '''    re.compile(r"(?<=api-key["': ]{1,3})([A-Za-z0-9_-]{20,})"),       # Qdrant/generic API keys in headers'''
new = """    re.compile(r'(?<=api-key["\\'\\': ]{1,3})([A-Za-z0-9_-]{20,})'),       # Qdrant/generic API keys in headers"""

if old in content:
    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)
    print("FIXED")
else:
    print("Pattern not found, checking current line 22:")
    for i, line in enumerate(content.splitlines(), 1):
        if i in (21, 22, 23):
            print(f"  {i}: {line}")
