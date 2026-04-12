#!/usr/bin/env python3
"""Dependency graph builder for local repos.

Usage:
    python dep-graph.py --repo story-engine --root /path/to/repo --build
    python dep-graph.py --repo story-engine --query apps/api/models/story.py --depth 2
    python dep-graph.py --repo VPAI --root /home/mobuone/VPAI --build
"""

from __future__ import annotations

import argparse
import ast as _ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------

PLANNING_INTEL_DIR = Path(__file__).parent.parent / ".planning" / "intel"


def graph_path(repo_name: str) -> Path:
    PLANNING_INTEL_DIR.mkdir(parents=True, exist_ok=True)
    return PLANNING_INTEL_DIR / f"dep-graph-{repo_name}.json"


# ---------------------------------------------------------------------------
# Import extraction helpers
# ---------------------------------------------------------------------------

def _resolve_py_import(module: str, dot_level: int, source_file: Path, repo_root: Path) -> str | None:
    """Resolve a Python import to a repo-relative path, or None if external."""
    if dot_level > 0:
        # Relative import — resolve from the directory of source_file
        base = source_file.parent
        for _ in range(dot_level - 1):
            base = base.parent
        if module:
            parts = module.split(".")
            candidate = base.joinpath(*parts).with_suffix(".py")
            if candidate.is_file():
                try:
                    return candidate.relative_to(repo_root).as_posix()
                except ValueError:
                    pass
            # Try as package (__init__.py)
            init = base.joinpath(*parts, "__init__.py")
            if init.is_file():
                try:
                    return init.relative_to(repo_root).as_posix()
                except ValueError:
                    pass
        return None
    else:
        # Absolute import — check if file exists anywhere in repo
        if not module:
            return None
        parts = module.split(".")
        candidate = repo_root.joinpath(*parts).with_suffix(".py")
        if candidate.is_file():
            return candidate.relative_to(repo_root).as_posix()
        init = repo_root.joinpath(*parts, "__init__.py")
        if init.is_file():
            return init.relative_to(repo_root).as_posix()
        return None


def extract_py_deps(path: Path, repo_root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = _ast.parse(text)
    except SyntaxError:
        return []
    deps: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.ImportFrom):
            resolved = _resolve_py_import(
                node.module or "", node.level, path, repo_root
            )
            if resolved:
                deps.append(resolved)
        elif isinstance(node, _ast.Import):
            for alias in node.names:
                resolved = _resolve_py_import(alias.name, 0, path, repo_root)
                if resolved:
                    deps.append(resolved)
    return list(dict.fromkeys(deps))  # deduplicate, preserve order


def _resolve_ts_import(raw: str, source_file: Path, repo_root: Path) -> str | None:
    """Resolve a TypeScript/JS import path to a repo-relative path."""
    if not raw.startswith("."):
        return None  # external or path-alias — skip
    base = source_file.parent / raw
    # IN-03: explicit extension (e.g. './foo.js') — check as-is before substituting
    if base.is_file():
        try:
            return base.relative_to(repo_root).as_posix()
        except ValueError:
            pass
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidate = base.with_suffix(ext)
        if candidate.is_file():
            try:
                return candidate.relative_to(repo_root).as_posix()
            except ValueError:
                pass
    # Try index file
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        index = base / f"index{ext}"
        if index.is_file():
            try:
                return index.relative_to(repo_root).as_posix()
            except ValueError:
                pass
    return None


def extract_ts_deps(path: Path, repo_root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    # IN-01: `from '...'` only — `require(...)` arm removed (causes false positives with RxJS `from()`)
    raw_imports = re.findall(r"""from\s+['"]([^'"]+)['"]""", text)
    deps: list[str] = []
    for raw in raw_imports:
        resolved = _resolve_ts_import(raw, path, repo_root)
        if resolved:
            deps.append(resolved)
    return list(dict.fromkeys(deps))


def _find_template_file(name: str, repo_root: Path) -> str | None:
    """Search for a Jinja2 template file in templates/ dirs."""
    for candidate in repo_root.rglob(f"templates/{name}"):
        try:
            return candidate.relative_to(repo_root).as_posix()
        except ValueError:
            pass
    return None


def extract_jinja_deps(path: Path, repo_root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    deps: list[str] = []
    # {% include 'file.j2' %}, {% import 'file.j2' %}
    for raw in re.findall(r"""{%-?\s+(?:include|import)\s+['"]([^'"]+)['"]""", text):
        resolved = _find_template_file(raw, repo_root)
        if resolved:
            deps.append(resolved)
    # Ansible task: template: src=foo.j2 or template: src: foo.j2
    for raw in re.findall(r"""template:\s+src[=:]\s*['"]?([^\s'"]+\.j2)['"]?""", text):
        resolved = _find_template_file(raw, repo_root)
        if resolved:
            deps.append(resolved)
    return list(dict.fromkeys(deps))


def extract_ansible_deps(path: Path, repo_root: Path) -> list[str]:
    """Extract template: references from Ansible task YAML files."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    deps: list[str] = []
    for raw in re.findall(r"""src[=:\s]+['"]?([^\s'"]+\.j2)['"]?""", text):
        resolved = _find_template_file(raw, repo_root)
        if resolved:
            deps.append(resolved)
    return list(dict.fromkeys(deps))


EXCLUDED_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".turbo",
    ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".worktrees", "coverage",
}

PY_EXTS = {".py"}
TS_EXTS = {".ts", ".tsx", ".js", ".jsx"}
JINJA_EXTS = {".j2"}
ANSIBLE_EXTS = {".yml", ".yaml"}


def build_graph(repo_root: Path) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for root, dirs, files in os.walk(repo_root):
        # Prune excluded dirs in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        root_path = Path(root)
        for fname in files:
            file_path = root_path / fname
            suffix = file_path.suffix.lower()
            try:
                rel = file_path.relative_to(repo_root).as_posix()
            except ValueError:
                continue

            deps: list[str] = []
            if suffix in PY_EXTS:
                deps = extract_py_deps(file_path, repo_root)
            elif suffix in TS_EXTS:
                deps = extract_ts_deps(file_path, repo_root)
            elif suffix in JINJA_EXTS:
                deps = extract_jinja_deps(file_path, repo_root)
            elif suffix in ANSIBLE_EXTS:
                deps = extract_ansible_deps(file_path, repo_root)

            if deps:
                graph[rel] = deps

    return graph


# ---------------------------------------------------------------------------
# BFS blast-radius
# ---------------------------------------------------------------------------

def blast_radius(graph: dict[str, list[str]], entry_file: str, depth: int = 3) -> dict[str, int]:
    """Return {file: depth} for all files reachable from entry_file."""
    visited: dict[str, int] = {entry_file: 0}
    queue = [entry_file]
    for current_depth in range(1, depth + 1):
        next_level = []
        for f in queue:
            for dep in graph.get(f, []):
                if dep not in visited:
                    visited[dep] = current_depth
                    next_level.append(dep)
        queue = next_level
        if not queue:
            break
    return visited


def reverse_graph(graph: dict[str, list[str]]) -> dict[str, list[str]]:
    """Build reverse adjacency list: who imports me?"""
    rev: dict[str, list[str]] = {}
    for src, deps in graph.items():
        for dep in deps:
            rev.setdefault(dep, []).append(src)
    return rev


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_build(args: argparse.Namespace) -> None:
    repo_root = Path(args.root).resolve()
    if not repo_root.is_dir():
        print(f"ERROR: --root {repo_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Building dependency graph for {args.repo} at {repo_root} …")
    graph = build_graph(repo_root)
    edge_count = sum(len(v) for v in graph.values())
    print(f"  {len(graph)} source files with dependencies, {edge_count} edges total")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": args.repo,
        "repo_root": str(repo_root),
        "graph": graph,
    }
    out_path = graph_path(args.repo)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  Written to {out_path}")


def cmd_query(args: argparse.Namespace) -> None:
    out_path = graph_path(args.repo)
    if not out_path.is_file():
        print(f"ERROR: no graph found at {out_path}. Run --build first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(out_path.read_text())
    graph = data["graph"]
    rev = reverse_graph(graph)

    query_file = args.query
    depth = int(args.depth)

    # WR-01: keep forward/reverse as separate dicts — merging overwrites bidirectional files
    # Forward blast-radius (what does query_file depend on transitively)
    fwd_results = {f: d for f, d in blast_radius(graph, query_file, depth).items() if f != query_file}
    # Reverse blast-radius (who depends on query_file transitively)
    rev_results = {f: d for f, d in blast_radius(rev, query_file, depth).items() if f != query_file}

    print(f"\nBlast-radius for: {query_file}  (depth={depth})")
    print(f"Repo: {data['repo']}  ({data['repo_root']})")
    print(f"Generated: {data['generated_at']}\n")

    if fwd_results:
        print(f"  DEPENDS ON (transitive, depth≤{depth}):")
        for f, d in sorted(fwd_results.items(), key=lambda x: (x[1], x[0])):
            print(f"    [d={d}] {f}")

    if rev_results:
        print(f"\n  IMPORTED BY (transitive, depth≤{depth}):")
        for f, d in sorted(rev_results.items(), key=lambda x: (x[1], x[0])):
            print(f"    [d={d}] {f}")

    total = len(fwd_results) + len(rev_results)
    print(f"\n  Total impacted files: {total}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dependency graph builder for local repos")
    parser.add_argument("--repo", required=True, help="Repo name (used for output filename)")
    parser.add_argument("--root", help="Repo root path (required for --build)")
    parser.add_argument("--build", action="store_true", help="Build and persist the dependency graph")
    parser.add_argument("--query", metavar="FILE", help="Query blast-radius for a repo-relative file path")
    parser.add_argument("--depth", default=3, type=int, help="BFS depth (default 3)")
    args = parser.parse_args()

    if args.build:
        if not args.root:
            parser.error("--root is required with --build")
        cmd_build(args)

    if args.query:
        cmd_query(args)

    if not args.build and not args.query:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
