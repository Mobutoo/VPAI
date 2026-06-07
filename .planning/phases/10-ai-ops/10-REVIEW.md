---
phase: 10-ai-ops
reviewed: 2026-04-12T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - /opt/workstation/ai-memory-worker/index.py
  - /home/mobuone/VPAI/roles/llamaindex-memory-worker/templates/index.py.j2
  - /home/mobuone/VPAI/roles/llamaindex-memory-worker/templates/config.yml.j2
  - /home/mobuone/VPAI/scripts/dep-graph.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-04-12
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Four files reviewed: the production memory-worker indexer (`index.py`), its Ansible Jinja2 deployment template (`index.py.j2`), the Qdrant config template (`config.yml.j2`), and the new stdlib-only dependency graph builder (`dep-graph.py`).

The code-graph layer is well-structured overall. No security vulnerabilities, no path traversal issues, no regex DoS exposure, and BFS cycle protection is correct. Two logic bugs were found: one in the blast-radius merge in `dep-graph.py` that silently drops forward edges when a file appears in both directions, and one in `extract_structural_meta` that misses plain `import X` statements for Python files.

The `config.yml.j2` and Jinja2 template are correct — the five new `payload_indexes` entries are properly structured and consistent with the metadata fields added to `to_text_nodes()`.

---

## Warnings

### WR-01: Blast-radius merge silently drops forward edges on bidirectional files

**File:** `/home/mobuone/VPAI/scripts/dep-graph.py:286-293`

**Issue:** The `cmd_query` function builds `combined` by first writing forward depths then overwriting with negative reverse depths. If file `X` is both a transitive dependency *and* a transitive dependent of the query file (common with shared utility modules), the second write at line 293 replaces the positive forward depth with a negative value. `fwd_items` then filters `d > 0` and silently drops `X` from the forward results. The file only appears in the reverse list at the wrong (reversed) depth.

```python
# Current — overwrites forward entry with reverse entry
for f, d in forward.items():
    if f != query_file:
        combined[f] = d          # depth=1 for shared util
for f, d in backward.items():
    if f != query_file:
        combined[f] = -d         # overwrites to -2 → disappears from fwd_items
```

**Fix:** Keep forward and reverse in separate dicts; never merge into `combined`. The display logic already iterates them separately via `fwd_items`/`rev_items`, so `combined` provides no benefit:

```python
# Replace the combined dict with direct separate dicts
fwd_results = {f: d for f, d in forward.items() if f != query_file}
rev_results = {f: d for f, d in backward.items() if f != query_file}

fwd_items = sorted(fwd_results.items(), key=lambda x: (x[1], x[0]))
rev_items = sorted(rev_results.items(), key=lambda x: (x[1], x[0]))
```

---

### WR-02: `extract_structural_meta` misses plain `import X` statements for Python files

**File:** `/opt/workstation/ai-memory-worker/index.py:249-253` (identical in `index.py.j2:249-253`)

**Issue:** The `imports` extraction in `extract_structural_meta` only walks `ast.ImportFrom` nodes (`from X import Y`). Plain `import os`, `import subprocess`, `import numpy as np` — i.e., `ast.Import` nodes — are entirely ignored. This is inconsistent with `dep-graph.py` lines 89-93 which correctly handles both node types. For code files like the worker itself (`import ast`, `import json`, `import subprocess`), the `imports` metadata field stored in Qdrant will be incomplete, degrading structural search quality.

```python
# Current — only handles ImportFrom
imports = list({
    node.module
    for node in _ast.walk(tree)
    if isinstance(node, _ast.ImportFrom) and node.module
})
```

**Fix:** Add `ast.Import` handling alongside `ast.ImportFrom`:

```python
import_from_mods = {
    node.module
    for node in _ast.walk(tree)
    if isinstance(node, _ast.ImportFrom) and node.module
}
import_mods = {
    alias.name.split(".")[0]          # top-level package name
    for node in _ast.walk(tree)
    if isinstance(node, _ast.Import)
    for alias in node.names
}
imports = list(import_from_mods | import_mods)
```

Apply the same fix to `index.py.j2` at the corresponding lines.

---

## Info

### IN-01: TS import regex produces false-positive edges on `from(...)` call expressions

**File:** `/home/mobuone/VPAI/scripts/dep-graph.py:122`

**Issue:** The regex alternation `(?:from|require)\s*\(\s*['"]([^'"]+)['"]` matches `from('path')` as an import. In JS/TS, `from` is not a callable, but code with a local function named `from` (e.g., RxJS `from(...)`) would produce spurious dependency edges if it happens to be passed a string literal. The impact is low (false edges, not missed edges) and heuristic accuracy is acceptable for this use case.

**Fix:** Remove the `from(...)` arm of the alternation; `require('...')` alone covers CJS imports and the `from '...'` arm covers ES module imports:

```python
raw_imports = re.findall(
    r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)|from\s+['"]([^'"]+)['"]""",
    text,
)
```

---

### IN-02: `extract_structural_meta` includes nested methods in `functions` list

**File:** `/opt/workstation/ai-memory-worker/index.py:244-247` (identical in `index.py.j2`)

**Issue:** `_ast.walk(tree)` is depth-first and visits all nodes unconditionally, so class methods appear alongside top-level functions in the `functions` metadata field. For a file with 3 top-level functions and a class with 8 methods, the field contains all 11 names. This is a design choice, but it means `functions` and `classes` overlap semantically (a class method appears in both). Worth noting if structural queries rely on `functions` meaning "top-level callable."

**Fix (optional):** To distinguish top-level functions from methods, walk only the module body:

```python
functions = [
    n.name for n in tree.body          # top-level only
    if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
]
```

No change needed if having all callables in `functions` is intentional.

---

### IN-03: `dep-graph.py` `_resolve_ts_import` does not handle imports with explicit extensions

**File:** `/home/mobuone/VPAI/scripts/dep-graph.py:101-103`

**Issue:** For an import like `import './foo.js'`, `Path('./foo.js').with_suffix('.ts')` produces `./foo.ts`, replacing the original `.js` extension. The loop never checks `./foo.js` itself, so the edge is missed. This only affects repos that mix `.js` and `.ts` files with explicit extensions in import paths (uncommon in strict TypeScript projects).

**Fix:** Check the path as-is before trying extension substitutions:

```python
base = source_file.parent / raw
# First: check if the path resolves directly (explicit extension)
if base.is_file():
    try:
        return base.relative_to(repo_root).as_posix()
    except ValueError:
        pass
# Then: try extension substitution
for ext in (".ts", ".tsx", ".js", ".jsx"):
    ...
```

---

_Reviewed: 2026-04-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
