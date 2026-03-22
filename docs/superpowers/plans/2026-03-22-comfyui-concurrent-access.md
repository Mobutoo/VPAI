# ComfyUI Concurrent Access — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable human (browser UI) and Claude CLI to collaboratively create, edit, execute, and version ComfyUI workflows simultaneously, with git history and Qdrant doc search.

**Architecture:** CLI-first (`comfyui-cli`) wrapping the ComfyUI HTTP API, with git auto-commit on writes, inotify watcher for browser changes, Qdrant semantic search for docs, and a thin MCP wrapper (`comfyui-studio`) that calls the CLI subprocess. All deployed via Ansible to the Workstation Pi.

**Tech Stack:** Python 3.12 (click, requests, pyyaml, qdrant-client, openai), Ansible, systemd, inotify-tools, git, MCP (mcp library)

**Spec:** `docs/superpowers/specs/2026-03-22-comfyui-concurrent-access-design.md`

---

## File Structure

### New files

```
roles/comfyui/files/comfyui-cli/
├── comfyui_cli/
│   ├── __init__.py          # Package version
│   ├── main.py              # Click entry point + global --json flag
│   ├── config.py            # YAML config loader + env var overrides
│   ├── api.py               # ComfyUI HTTP client (all endpoints)
│   ├── workflows.py         # Click group: list, get, save, delete, rename
│   ├── execution.py         # Click group: exec, queue, cancel, history, output
│   ├── introspection.py     # Click commands: nodes, models, upload, status
│   ├── versioning.py        # Click commands: versions, revert, diff
│   ├── docs.py              # Click command: docs (Qdrant search)
│   ├── converter.py         # UI-format → API-format conversion
│   └── git_ops.py           # Git commit/push helpers
├── tests/
│   ├── conftest.py          # Shared fixtures (mock config, mock API responses)
│   ├── test_config.py       # Config loader tests
│   ├── test_converter.py    # UI→API conversion tests
│   └── test_git_ops.py      # Git operations tests
├── requirements.txt         # Runtime deps
├── requirements-dev.txt     # Test deps (pytest)
└── setup.py                 # Setuptools with console_scripts entry point

roles/comfyui/files/comfyui-studio/
└── mcp_server.py            # MCP wrapper calling CLI subprocess

roles/comfyui/templates/
├── comfyui-cli.yaml.j2      # CLI config (deployed to ~/.comfyui-cli.yaml)
├── comfyui-watcher.sh.j2    # inotify watcher bash script
└── comfyui-watcher.service.j2  # systemd unit for watcher
```

### Modified files

```
roles/comfyui/defaults/main.yml               # Add new variables
roles/comfyui/templates/docker-compose-creative.yml.j2  # Add user volume mount
roles/comfyui/tasks/main.yml                   # Add tasks for CLI, git, watcher, MCP
roles/comfyui/handlers/main.yml                # Add watcher restart handler
```

---

## Phase 1: Foundation (Volume Fix + CLI Core)

### Task 1: Docker Volume Fix + Ansible Defaults

Add the `/app/user` volume mount and new default variables for the concurrent access features.

**Files:**
- Modify: `roles/comfyui/defaults/main.yml`
- Modify: `roles/comfyui/templates/docker-compose-creative.yml.j2:30-35`

- [ ] **Step 1: Add new defaults**

Add to `roles/comfyui/defaults/main.yml` at the end:

```yaml
# --- Concurrent Access (CLI + browser) ---
# Workflows directory (inside user volume, ComfyUI v0.17.1+ default profile)
comfyui_workflows_dir: "{{ comfyui_data_dir }}/user/default/workflows"

# CLI config
comfyui_cli_install_dir: "/opt/workstation/comfyui-cli"
comfyui_cli_author_name: "Claude CLI"
comfyui_cli_author_email: "claude@localhost"

# MCP server
comfyui_studio_install_dir: "/opt/workstation/comfyui-studio"

# Git versioning
comfyui_git_enabled: true
comfyui_git_remote: "git@seko-vpn:mobuone/comfyui-workflows.git"
comfyui_git_push_interval: 5  # minutes

# Qdrant doc search
comfyui_qdrant_url: "https://qd.ewutelo.cloud"
comfyui_qdrant_collection: "comfyui-docs"
```

- [ ] **Step 2: Add user volume mount to Docker Compose**

In `roles/comfyui/templates/docker-compose-creative.yml.j2`, add the user volume in the comfyui service volumes section (after the creative-assets line):

```yaml
      - {{ comfyui_data_dir }}/user:/app/user
```

- [ ] **Step 3: Commit**

```bash
git add roles/comfyui/defaults/main.yml roles/comfyui/templates/docker-compose-creative.yml.j2
git commit -m "feat(comfyui): add user volume mount + concurrent access defaults"
```

---

### Task 2: CLI Scaffold — Config + API Client

Create the CLI package skeleton with config loader and HTTP client.

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/__init__.py`
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/config.py`
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/api.py`
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/main.py`
- Create: `roles/comfyui/files/comfyui-cli/requirements.txt`
- Create: `roles/comfyui/files/comfyui-cli/requirements-dev.txt`
- Create: `roles/comfyui/files/comfyui-cli/setup.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/conftest.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/test_config.py`

- [ ] **Step 1: Create `__init__.py`**

```python
"""comfyui-cli — CLI tool for ComfyUI workflow management."""
__version__ = "0.1.0"
```

- [ ] **Step 2: Create `config.py`**

```python
"""Configuration loader for comfyui-cli.

Loads from ~/.comfyui-cli.yaml with env var overrides.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".comfyui-cli.yaml"

DEFAULTS = {
    "comfyui_url": "http://localhost:8188",
    "workflows_dir": "/opt/workstation/data/comfyui/user/default/workflows",
    "git_enabled": True,
    "git_author_name": "Claude CLI",
    "git_author_email": "claude@localhost",
    "qdrant_url": "",
    "qdrant_api_key": "",
    "qdrant_collection": "comfyui-docs",
    "litellm_url": "",
    "litellm_api_key": "",
}

ENV_MAP = {
    "COMFYUI_URL": "comfyui_url",
    "COMFYUI_WORKFLOWS_DIR": "workflows_dir",
    "COMFYUI_GIT_ENABLED": "git_enabled",
    "QDRANT_URL": "qdrant_url",
    "QDRANT_API_KEY": "qdrant_api_key",
    "LITELLM_BASE_URL": "litellm_url",
    "LITELLM_API_KEY": "litellm_api_key",
}


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load config from YAML file, then override with env vars."""
    path = config_path or DEFAULT_CONFIG_PATH
    config = dict(DEFAULTS)

    if path.exists():
        with open(path) as f:
            file_config = yaml.safe_load(f) or {}
        config.update(file_config)

    # Env var overrides
    for env_key, config_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            if config_key == "git_enabled":
                config[config_key] = val.lower() in ("true", "1", "yes")
            else:
                config[config_key] = val

    return config
```

- [ ] **Step 3: Create `api.py`**

```python
"""ComfyUI HTTP API client.

Wraps all ComfyUI REST endpoints used by the CLI.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests


class ComfyUIClient:
    """HTTP client for ComfyUI API."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(
            f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )

    def _post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(
            f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )

    # --- System ---

    def system_stats(self) -> Dict[str, Any]:
        """GET /system_stats"""
        return self._get("/system_stats").json()

    # --- Workflows (userdata) ---

    def list_workflows(self) -> List[str]:
        """GET /userdata?dir=workflows — list workflow files."""
        resp = self._get("/userdata", params={"dir": "workflows", "recurse": "true"})
        resp.raise_for_status()
        return resp.json()

    def get_workflow(self, path: str) -> Dict[str, Any]:
        """GET /userdata/workflows/<path> — read workflow JSON."""
        resp = self._get(f"/userdata/workflows/{quote(path, safe='/')}")
        resp.raise_for_status()
        return resp.json()

    def save_workflow(self, path: str, data: Dict[str, Any]) -> None:
        """POST /userdata/workflows/<path> — save workflow JSON."""
        resp = self._post(
            f"/userdata/workflows/{quote(path, safe='/')}",
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
            params={"overwrite": "true"},
        )
        resp.raise_for_status()

    def delete_workflow(self, path: str) -> None:
        """DELETE /userdata/workflows/<path>"""
        resp = self.session.delete(
            f"{self.base_url}/userdata/workflows/{quote(path, safe='/')}",
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def move_workflow(self, old_path: str, new_path: str) -> None:
        """POST /userdata/workflows/<old>?rename=<new> — rename/move."""
        resp = self._post(
            f"/userdata/workflows/{quote(old_path, safe='/')}",
            params={"rename": new_path},
        )
        resp.raise_for_status()

    # --- Execution ---

    def queue_prompt(self, prompt: Dict[str, Any], client_id: str = "") -> Dict:
        """POST /prompt — queue a workflow for execution."""
        payload = {"prompt": prompt}
        if client_id:
            payload["client_id"] = client_id
        resp = self._post("/prompt", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_queue(self) -> Dict[str, Any]:
        """GET /queue — running + pending items."""
        return self._get("/queue").json()

    def cancel(self, prompt_id: Optional[str] = None) -> None:
        """Cancel a specific prompt or interrupt + clear all."""
        if prompt_id:
            self._post("/queue", json={"delete": [prompt_id]})
        else:
            # Interrupt currently running + clear pending queue
            self._post("/interrupt")
            self._post("/queue", json={"clear": True})

    def get_history(self, limit: int = 10) -> Dict[str, Any]:
        """GET /history — execution history."""
        return self._get("/history", params={"max_items": str(limit)}).json()

    def get_prompt_output(self, prompt_id: str) -> Dict[str, Any]:
        """GET /history/<prompt_id> — specific execution result."""
        resp = self._get(f"/history/{prompt_id}")
        resp.raise_for_status()
        data = resp.json()
        return data.get(prompt_id, {})

    # --- Introspection ---

    def get_object_info(self, node_class: Optional[str] = None) -> Dict[str, Any]:
        """GET /object_info[/<class>] — node class metadata."""
        path = f"/object_info/{node_class}" if node_class else "/object_info"
        return self._get(path).json()

    def get_models(self, folder: Optional[str] = None) -> Any:
        """GET /models[/<folder>] — available models."""
        path = f"/models/{folder}" if folder else "/models"
        return self._get(path).json()

    def upload_image(self, file_path: str, subfolder: str = "") -> Dict[str, Any]:
        """POST /upload/image — upload an image file."""
        with open(file_path, "rb") as f:
            files = {"image": (Path(file_path).name, f, "image/png")}
            data = {}
            if subfolder:
                data["subfolder"] = subfolder
            resp = self._post("/upload/image", files=files, data=data)
        resp.raise_for_status()
        return resp.json()

    def get_view(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """GET /view — download an output image."""
        resp = self._get(
            "/view",
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
        )
        resp.raise_for_status()
        return resp.content

    # --- Polling ---

    def wait_for_completion(self, prompt_id: str, poll_interval: float = 2.0, timeout: float = 300.0) -> Dict:
        """Poll /history until prompt_id appears with status."""
        start = time.time()
        while time.time() - start < timeout:
            history = self.get_history(limit=50)
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False) or status.get("status_str") == "success":
                    return entry
                if status.get("status_str") == "error":
                    return entry
            time.sleep(poll_interval)
        raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")
```

- [ ] **Step 4: Create `main.py`**

```python
"""comfyui-cli entry point.

Global --json flag, click group structure.
"""
import json as json_module
import sys

import click

from . import __version__
from .config import load_config
from .api import ComfyUIClient


class Context:
    """Shared CLI context."""

    def __init__(self):
        self.config = {}
        self.client = None
        self.json_output = False

    def output(self, data, human_format_fn=None):
        """Output data as JSON or human-readable."""
        if self.json_output:
            click.echo(json_module.dumps(data, indent=2, ensure_ascii=False))
        elif human_format_fn:
            click.echo(human_format_fn(data))
        else:
            click.echo(json_module.dumps(data, indent=2, ensure_ascii=False))

    def error(self, msg: str, exit_code: int = 1):
        """Print error and exit."""
        if self.json_output:
            click.echo(json_module.dumps({"error": msg}), err=True)
        else:
            click.echo(f"Error: {msg}", err=True)
        sys.exit(exit_code)


pass_ctx = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.option("--json", "json_output", is_flag=True, help="Machine-parseable JSON output")
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config file path")
@click.version_option(version=__version__)
@pass_ctx
def cli(ctx, json_output, config_path):
    """comfyui-cli — ComfyUI workflow management CLI."""
    from pathlib import Path

    config_p = Path(config_path) if config_path else None
    ctx.config = load_config(config_p)
    ctx.json_output = json_output
    ctx.client = ComfyUIClient(ctx.config["comfyui_url"])


def main():
    """Entry point for console_scripts."""
    # Import and register all command groups
    from . import workflows, execution, introspection, versioning, docs  # noqa: F401
    cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create `requirements.txt` and `requirements-dev.txt`**

`requirements.txt`:
```
click>=8.1,<9
requests>=2.31,<3
pyyaml>=6.0,<7
qdrant-client>=1.9,<2
openai>=1.30,<2
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.0,<9
pytest-mock>=3.12,<4
```

- [ ] **Step 6: Create `setup.py`**

```python
from setuptools import setup, find_packages

setup(
    name="comfyui-cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1,<9",
        "requests>=2.31,<3",
        "pyyaml>=6.0,<7",
    ],
    extras_require={
        "docs": ["qdrant-client>=1.9,<2", "openai>=1.30,<2"],
    },
    entry_points={
        "console_scripts": [
            "comfyui-cli=comfyui_cli.main:main",
        ],
    },
    python_requires=">=3.10",
)
```

- [ ] **Step 7: Create test fixtures**

Create `tests/__init__.py` (empty file):
```python
```

Create `tests/conftest.py`:
```python
"""Shared test fixtures for comfyui-cli."""
import pytest
from unittest.mock import MagicMock
from comfyui_cli.config import DEFAULTS


@pytest.fixture
def mock_config():
    """Default config for tests."""
    return dict(DEFAULTS)


@pytest.fixture
def mock_api():
    """Mock ComfyUI API client."""
    client = MagicMock()
    client.base_url = "http://localhost:8188"
    return client
```

- [ ] **Step 8: Write config tests**

`tests/test_config.py`:
```python
"""Tests for config loader."""
import os
import pytest
from pathlib import Path
from comfyui_cli.config import load_config, DEFAULTS


def test_defaults_when_no_file(tmp_path):
    """Config returns defaults when file doesn't exist."""
    config = load_config(tmp_path / "nonexistent.yaml")
    assert config["comfyui_url"] == "http://localhost:8188"
    assert config["git_enabled"] is True


def test_file_overrides(tmp_path):
    """YAML file values override defaults."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("comfyui_url: http://other:9999\n")
    config = load_config(cfg_file)
    assert config["comfyui_url"] == "http://other:9999"
    assert config["workflows_dir"] == DEFAULTS["workflows_dir"]


def test_env_overrides(tmp_path, monkeypatch):
    """Env vars override file values."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("comfyui_url: http://file:1234\n")
    monkeypatch.setenv("COMFYUI_URL", "http://env:5678")
    config = load_config(cfg_file)
    assert config["comfyui_url"] == "http://env:5678"


def test_git_enabled_env_bool(tmp_path, monkeypatch):
    """COMFYUI_GIT_ENABLED env var parsed as bool."""
    monkeypatch.setenv("COMFYUI_GIT_ENABLED", "false")
    config = load_config(tmp_path / "nope.yaml")
    assert config["git_enabled"] is False
```

- [ ] **Step 9: Run tests**

```bash
cd roles/comfyui/files/comfyui-cli && pip install -e ".[docs]" -r requirements-dev.txt && pytest tests/test_config.py -v
```

Expected: 4 PASS

- [ ] **Step 10: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/
git commit -m "feat(comfyui): CLI scaffold — config, API client, entry point"
```

---

### Task 3: Workflow CRUD Commands

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/workflows.py`

- [ ] **Step 1: Create `workflows.py`**

```python
"""Workflow CRUD commands: list, get, save, delete, rename."""
import json
import sys

import click

from .main import cli, pass_ctx


@cli.group()
def workflows():
    """Manage ComfyUI workflows."""
    pass


@workflows.command("list")
@pass_ctx
def list_workflows(ctx):
    """List all workflows."""
    try:
        items = ctx.client.list_workflows()
    except Exception as e:
        ctx.error(str(e))

    def human(data):
        if not data:
            return "No workflows found."
        return "\n".join(f"  {f}" for f in sorted(data))

    ctx.output(items, human)


@workflows.command("get")
@click.argument("path")
@click.option("--raw", is_flag=True, help="Raw API response")
@pass_ctx
def get_workflow(ctx, path, raw):
    """Read a workflow JSON file."""
    try:
        data = ctx.client.get_workflow(path)
    except Exception as e:
        ctx.error(f"Cannot read '{path}': {e}")

    if raw:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        summary = {
            "path": path,
            "nodes": len(data.get("nodes", [])) if "nodes" in data else "N/A (API format)",
            "links": len(data.get("links", [])) if "links" in data else "N/A",
        }
        def human(d):
            return f"Workflow: {d['path']}\n  Nodes: {d['nodes']}\n  Links: {d['links']}"

        ctx.output(summary if not ctx.json_output else data, human)


@workflows.command("save")
@click.argument("path")
@click.option("--file", "input_file", type=click.Path(exists=True), help="JSON file to upload")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read JSON from stdin")
@pass_ctx
def save_workflow(ctx, path, input_file, from_stdin):
    """Save a workflow JSON file."""
    if input_file:
        with open(input_file) as f:
            data = json.load(f)
    elif from_stdin:
        data = json.load(sys.stdin)
    else:
        ctx.error("Provide --file or --stdin")

    try:
        ctx.client.save_workflow(path, data)
    except Exception as e:
        ctx.error(f"Cannot save '{path}': {e}")

    # Git commit if enabled
    if ctx.config.get("git_enabled"):
        from .git_ops import git_commit
        git_commit(ctx.config, f"cli: save {path}", [path])

    ctx.output({"status": "saved", "path": path}, lambda d: f"Saved: {d['path']}")


@workflows.command("delete")
@click.argument("path")
@pass_ctx
def delete_workflow(ctx, path):
    """Delete a workflow."""
    try:
        ctx.client.delete_workflow(path)
    except Exception as e:
        ctx.error(f"Cannot delete '{path}': {e}")

    if ctx.config.get("git_enabled"):
        from .git_ops import git_commit
        git_commit(ctx.config, f"cli: delete {path}", [path], delete=True)

    ctx.output({"status": "deleted", "path": path}, lambda d: f"Deleted: {d['path']}")


@workflows.command("rename")
@click.argument("old_path")
@click.argument("new_path")
@pass_ctx
def rename_workflow(ctx, old_path, new_path):
    """Rename or move a workflow."""
    try:
        ctx.client.move_workflow(old_path, new_path)
    except Exception as e:
        ctx.error(f"Cannot rename '{old_path}': {e}")

    if ctx.config.get("git_enabled"):
        from .git_ops import git_commit
        git_commit(ctx.config, f"cli: rename {old_path} -> {new_path}", [old_path, new_path])

    ctx.output(
        {"status": "renamed", "old": old_path, "new": new_path},
        lambda d: f"Renamed: {d['old']} -> {d['new']}",
    )
```

- [ ] **Step 2: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/workflows.py
git commit -m "feat(comfyui): CLI workflow CRUD commands"
```

---

### Task 4: Execution Commands

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/execution.py`

- [ ] **Step 1: Create `execution.py`**

```python
"""Execution commands: exec, queue, cancel, history, output."""
import json
import os
import uuid
from pathlib import Path

import click

from .main import cli, pass_ctx


# --- Simple default workflow for --prompt shortcut ---
DEFAULT_PROMPT_WORKFLOW = {
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "blurry, bad quality, deformed", "clip": ["4", 1]},
    },
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": ""},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-cli", "images": ["8", 0]},
    },
}


@cli.command("exec")
@click.argument("workflow_path", required=False)
@click.option("--prompt", "text_prompt", help="Text prompt (uses default workflow)")
@click.option("--param", multiple=True, help="Override param: key=value")
@click.option("--width", type=int, default=512)
@click.option("--height", type=int, default=512)
@click.option("--seed", type=int, default=None)
@click.option("--wait", "do_wait", is_flag=True, help="Wait for completion")
@pass_ctx
def exec_workflow(ctx, workflow_path, text_prompt, param, width, height, seed, do_wait):
    """Execute a workflow or a simple text prompt."""
    if text_prompt:
        # Simple prompt shortcut — use default workflow (deep copy to avoid mutating global)
        import copy
        api_workflow = copy.deepcopy(DEFAULT_PROMPT_WORKFLOW)
        api_workflow["6"]["inputs"]["text"] = text_prompt
        api_workflow["5"]["inputs"]["width"] = width
        api_workflow["5"]["inputs"]["height"] = height
        if seed is not None:
            api_workflow["3"]["inputs"]["seed"] = seed
        else:
            import random
            api_workflow["3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)
        # Find first available checkpoint
        try:
            models = ctx.client.get_models("checkpoints")
            if models:
                api_workflow["4"]["inputs"]["ckpt_name"] = models[0]
            else:
                ctx.error("No checkpoint models found. Upload a model first.")
        except Exception:
            ctx.error("Cannot list models. Is ComfyUI running?")

    elif workflow_path:
        # Load workflow from file or API
        try:
            workflow_data = ctx.client.get_workflow(workflow_path)
        except Exception as e:
            ctx.error(f"Cannot load workflow '{workflow_path}': {e}")

        # Detect format: UI format has 'nodes' key, API format has node IDs with class_type
        if "nodes" in workflow_data:
            from .converter import ui_to_api
            try:
                object_info = ctx.client.get_object_info()
                api_workflow = ui_to_api(workflow_data, object_info)
            except Exception as e:
                ctx.error(f"UI→API conversion failed: {e}")
        else:
            api_workflow = workflow_data

        # Apply --param overrides
        for p in param:
            if "=" not in p:
                ctx.error(f"Invalid param format '{p}', use key=value (e.g., 3.inputs.seed=42)")
            key, val = p.split("=", 1)
            parts = key.split(".")
            target = api_workflow
            for part in parts[:-1]:
                target = target.get(part, {})
            try:
                target[parts[-1]] = json.loads(val)
            except json.JSONDecodeError:
                target[parts[-1]] = val
    else:
        ctx.error("Provide a workflow path or --prompt")

    # Submit
    try:
        result = ctx.client.queue_prompt(api_workflow)
        prompt_id = result.get("prompt_id", "unknown")
    except Exception as e:
        ctx.error(f"Execution failed: {e}")

    if do_wait:
        try:
            entry = ctx.client.wait_for_completion(prompt_id)
            ctx.output({"prompt_id": prompt_id, "status": "completed", "outputs": entry.get("outputs", {})})
        except TimeoutError:
            ctx.error(f"Timeout waiting for {prompt_id}")
    else:
        ctx.output(
            {"prompt_id": prompt_id, "status": "queued"},
            lambda d: f"Queued: {d['prompt_id']}",
        )


@cli.command("queue")
@pass_ctx
def queue_status(ctx):
    """Show current queue."""
    try:
        data = ctx.client.get_queue()
    except Exception as e:
        ctx.error(str(e))

    def human(d):
        running = d.get("queue_running", [])
        pending = d.get("queue_pending", [])
        lines = [f"Running: {len(running)}", f"Pending: {len(pending)}"]
        for item in running:
            lines.append(f"  [running] {item[1] if len(item) > 1 else 'unknown'}")
        for item in pending:
            lines.append(f"  [pending] {item[1] if len(item) > 1 else 'unknown'}")
        return "\n".join(lines)

    ctx.output(data, human)


@cli.command("cancel")
@click.argument("prompt_id", required=False)
@click.option("--all", "cancel_all", is_flag=True, help="Cancel all")
@pass_ctx
def cancel_prompt(ctx, prompt_id, cancel_all):
    """Cancel a queued prompt."""
    try:
        if cancel_all:
            ctx.client.cancel()
        elif prompt_id:
            ctx.client.cancel(prompt_id)
        else:
            ctx.error("Provide a prompt_id or --all")
    except Exception as e:
        ctx.error(str(e))
    ctx.output({"status": "cancelled"}, lambda d: "Cancelled.")


@cli.command("history")
@click.option("--limit", default=10, help="Max items")
@pass_ctx
def history(ctx, limit):
    """Show execution history."""
    try:
        data = ctx.client.get_history(limit)
    except Exception as e:
        ctx.error(str(e))

    def human(d):
        if not d:
            return "No history."
        lines = []
        for pid, entry in list(d.items())[:limit]:
            status = entry.get("status", {}).get("status_str", "unknown")
            lines.append(f"  {pid[:12]}...  {status}")
        return "\n".join(lines)

    ctx.output(data, human)


@cli.command("output")
@click.argument("prompt_id")
@click.option("--save-to", type=click.Path(), help="Save output images to directory")
@pass_ctx
def output(ctx, prompt_id, save_to):
    """Retrieve outputs for a completed prompt."""
    try:
        entry = ctx.client.get_prompt_output(prompt_id)
    except Exception as e:
        ctx.error(str(e))

    if not entry:
        ctx.error(f"No output found for {prompt_id}")

    outputs = entry.get("outputs", {})

    if save_to:
        save_dir = Path(save_to)
        save_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                filename = img["filename"]
                subfolder = img.get("subfolder", "")
                data = ctx.client.get_view(filename, subfolder)
                dest = save_dir / filename
                dest.write_bytes(data)
                saved.append(str(dest))
        ctx.output({"saved": saved}, lambda d: "\n".join(f"  Saved: {f}" for f in d["saved"]))
    else:
        ctx.output(outputs)
```

- [ ] **Step 2: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/execution.py
git commit -m "feat(comfyui): CLI execution commands — exec, queue, cancel, history, output"
```

---

### Task 5: Introspection + Status Commands

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/introspection.py`

- [ ] **Step 1: Create `introspection.py`**

```python
"""Introspection commands: nodes, models, upload, status."""
import json

import click

from .main import cli, pass_ctx


@cli.command("nodes")
@click.argument("node_class", required=False)
@pass_ctx
def nodes(ctx, node_class):
    """List node classes or show details for one."""
    try:
        data = ctx.client.get_object_info(node_class)
    except Exception as e:
        ctx.error(str(e))

    if node_class:
        ctx.output(data)
    else:
        def human(d):
            classes = sorted(d.keys())
            return f"{len(classes)} node classes:\n" + "\n".join(f"  {c}" for c in classes)
        ctx.output(data, human)


@cli.command("models")
@click.argument("folder", required=False)
@pass_ctx
def models(ctx, folder):
    """List available models."""
    try:
        data = ctx.client.get_models(folder)
    except Exception as e:
        ctx.error(str(e))

    def human(d):
        if isinstance(d, list):
            return "\n".join(f"  {m}" for m in d) if d else "No models found."
        return json.dumps(d, indent=2)

    ctx.output(data, human)


@cli.command("upload")
@click.argument("image_path", type=click.Path(exists=True))
@click.option("--subfolder", default="", help="Target subfolder")
@pass_ctx
def upload(ctx, image_path, subfolder):
    """Upload an image to ComfyUI."""
    try:
        result = ctx.client.upload_image(image_path, subfolder)
    except Exception as e:
        ctx.error(str(e))

    ctx.output(result, lambda d: f"Uploaded: {d.get('name', 'unknown')}")


@cli.command("status")
@pass_ctx
def status(ctx):
    """Show ComfyUI system status."""
    try:
        data = ctx.client.system_stats()
    except Exception as e:
        ctx.error(str(e))

    def human(d):
        sys_info = d.get("system", {})
        lines = [
            f"ComfyUI: {ctx.config['comfyui_url']}",
            f"  OS: {sys_info.get('os', '?')}",
            f"  Python: {sys_info.get('python_version', '?')}",
            f"  RAM: {sys_info.get('ram_total', 0) // (1024**3)}GB",
        ]
        devices = d.get("devices", [])
        for dev in devices:
            lines.append(f"  Device: {dev.get('name', '?')} ({dev.get('type', '?')})")
        return "\n".join(lines)

    ctx.output(data, human)
```

- [ ] **Step 2: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/introspection.py
git commit -m "feat(comfyui): CLI introspection commands — nodes, models, upload, status"
```

---

## Phase 2: Versioning (Git + inotify)

### Task 6: Git Operations Module

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/git_ops.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/test_git_ops.py`

- [ ] **Step 1: Create `git_ops.py`**

```python
"""Git integration for workflow versioning.

All git operations are non-blocking — errors are logged but don't fail the CLI command.
"""
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


def _run_git(workflows_dir: str, args: List[str], env_override: Optional[Dict] = None) -> subprocess.CompletedProcess:
    """Run a git command in the workflows directory."""
    cmd = ["git"] + args
    return subprocess.run(
        cmd,
        cwd=workflows_dir,
        capture_output=True,
        text=True,
        timeout=30,
        env=env_override,
    )


def is_git_repo(workflows_dir: str) -> bool:
    """Check if the workflows directory is a git repo."""
    result = _run_git(workflows_dir, ["rev-parse", "--git-dir"])
    return result.returncode == 0


def git_commit(config: Dict, message: str, paths: List[str], delete: bool = False) -> bool:
    """Stage and commit changes with CLI attribution.

    Returns True if commit was made, False otherwise.
    Non-blocking: errors are logged but don't raise.
    """
    workflows_dir = config.get("workflows_dir", "")
    if not workflows_dir or not is_git_repo(workflows_dir):
        return False

    author_name = config.get("git_author_name", "Claude CLI")
    author_email = config.get("git_author_email", "claude@localhost")

    try:
        # Stage changes
        if delete:
            _run_git(workflows_dir, ["add", "-A"])
        else:
            _run_git(workflows_dir, ["add", "--"] + paths)

        # Check if there's anything to commit
        result = _run_git(workflows_dir, ["diff", "--cached", "--quiet"])
        if result.returncode == 0:
            log.debug("No changes to commit")
            return False

        # Commit with attribution
        result = _run_git(
            workflows_dir,
            [
                "-c", f"user.name={author_name}",
                "-c", f"user.email={author_email}",
                "commit", "-m", message,
            ],
        )

        if result.returncode == 0:
            log.info("Committed: %s", message)
            return True
        else:
            log.warning("Git commit failed: %s", result.stderr)
            return False

    except Exception as e:
        log.warning("Git error: %s", e)
        return False


def git_log(workflows_dir: str, path: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Get git log entries, optionally filtered to a specific file."""
    args = [
        "log", f"--max-count={limit}",
        "--format=%H|%an|%ae|%at|%s",
    ]
    if path:
        args += ["--", path]

    result = _run_git(workflows_dir, args)
    if result.returncode != 0:
        return []

    entries = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) == 5:
            entries.append({
                "commit": parts[0],
                "author_name": parts[1],
                "author_email": parts[2],
                "timestamp": int(parts[3]),
                "message": parts[4],
            })
    return entries


def git_diff(workflows_dir: str, path: Optional[str] = None, commit: Optional[str] = None) -> str:
    """Show diff for a file, optionally against a specific commit."""
    args = ["diff"]
    if commit:
        args.append(commit)
    args.append("--")
    if path:
        args.append(path)

    result = _run_git(workflows_dir, args)
    return result.stdout if result.returncode == 0 else ""


def git_show(workflows_dir: str, commit: str, path: str) -> str:
    """Show file content at a specific commit."""
    result = _run_git(workflows_dir, ["show", f"{commit}:{path}"])
    return result.stdout if result.returncode == 0 else ""


def git_revert_file(config: Dict, path: str, commit: str) -> bool:
    """Restore a file to a specific commit version."""
    workflows_dir = config.get("workflows_dir", "")
    if not workflows_dir or not is_git_repo(workflows_dir):
        return False

    try:
        # Get file content at that commit
        content = git_show(workflows_dir, commit, path)
        if not content:
            return False

        # Write file
        full_path = Path(workflows_dir) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

        # Commit the revert
        return git_commit(config, f"cli: revert {path} to {commit[:8]}", [path])

    except Exception as e:
        log.warning("Revert failed: %s", e)
        return False
```

- [ ] **Step 2: Write tests**

`tests/test_git_ops.py`:
```python
"""Tests for git operations."""
import json
import subprocess
import pytest
from pathlib import Path
from comfyui_cli.git_ops import is_git_repo, git_commit, git_log


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test", "commit", "--allow-empty", "-m", "init"],
        cwd=tmp_path, capture_output=True,
    )
    return tmp_path


@pytest.fixture
def git_config(git_repo):
    """Config pointing at the temp git repo."""
    return {
        "workflows_dir": str(git_repo),
        "git_enabled": True,
        "git_author_name": "Test CLI",
        "git_author_email": "test@localhost",
    }


def test_is_git_repo(git_repo, tmp_path):
    assert is_git_repo(str(git_repo)) is True
    assert is_git_repo(str(tmp_path / "nonexistent")) is False


def test_git_commit(git_config, git_repo):
    # Create a file to commit
    (git_repo / "test.json").write_text('{"test": true}')
    result = git_commit(git_config, "cli: test commit", ["test.json"])
    assert result is True


def test_git_commit_no_changes(git_config, git_repo):
    result = git_commit(git_config, "cli: no changes", [])
    assert result is False


def test_git_log(git_config, git_repo):
    (git_repo / "wf.json").write_text('{"nodes": []}')
    git_commit(git_config, "cli: add wf", ["wf.json"])
    entries = git_log(str(git_repo), limit=5)
    assert len(entries) >= 1
    assert entries[0]["author_name"] == "Test CLI"
    assert "cli: add wf" in entries[0]["message"]
```

- [ ] **Step 3: Run tests**

```bash
cd roles/comfyui/files/comfyui-cli && pytest tests/test_git_ops.py -v
```

Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/git_ops.py roles/comfyui/files/comfyui-cli/tests/test_git_ops.py
git commit -m "feat(comfyui): CLI git operations module with tests"
```

---

### Task 7: Version Commands

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/versioning.py`

- [ ] **Step 1: Create `versioning.py`**

```python
"""Version commands: versions, revert, diff."""
import json
from datetime import datetime

import click

from .main import cli, pass_ctx
from .git_ops import git_log, git_diff, git_revert_file


@cli.command("versions")
@click.argument("workflow_path")
@click.option("--limit", default=10, help="Max entries")
@pass_ctx
def versions(ctx, workflow_path, limit):
    """Show version history for a workflow."""
    workflows_dir = ctx.config.get("workflows_dir", "")
    entries = git_log(workflows_dir, path=workflow_path, limit=limit)

    if not entries:
        ctx.error(f"No version history for '{workflow_path}'")

    def human(data):
        lines = [f"Versions of {workflow_path}:"]
        for e in data:
            ts = datetime.fromtimestamp(e["timestamp"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {e['commit'][:8]}  {ts}  [{e['author_name']}]  {e['message']}")
        return "\n".join(lines)

    ctx.output(entries, human)


@cli.command("revert")
@click.argument("workflow_path")
@click.argument("commit_sha")
@pass_ctx
def revert(ctx, workflow_path, commit_sha):
    """Revert a workflow to a specific version."""
    success = git_revert_file(ctx.config, workflow_path, commit_sha)
    if not success:
        ctx.error(f"Cannot revert '{workflow_path}' to {commit_sha}")

    # Also update via API so ComfyUI picks up the change
    from pathlib import Path
    full_path = Path(ctx.config["workflows_dir"]) / workflow_path
    if full_path.exists():
        data = json.loads(full_path.read_text())
        try:
            ctx.client.save_workflow(workflow_path, data)
        except Exception:
            pass  # File is already reverted on disk

    ctx.output(
        {"status": "reverted", "path": workflow_path, "commit": commit_sha},
        lambda d: f"Reverted {d['path']} to {d['commit'][:8]}",
    )


@cli.command("diff")
@click.argument("workflow_path")
@click.argument("commit_sha", required=False)
@pass_ctx
def diff(ctx, workflow_path, commit_sha):
    """Show diff for a workflow."""
    workflows_dir = ctx.config.get("workflows_dir", "")
    result = git_diff(workflows_dir, path=workflow_path, commit=commit_sha)

    if not result:
        ctx.output({"diff": "", "message": "No changes"}, lambda d: "No changes.")
    elif ctx.json_output:
        ctx.output({"diff": result})
    else:
        click.echo(result)
```

- [ ] **Step 2: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/versioning.py
git commit -m "feat(comfyui): CLI version commands — versions, revert, diff"
```

---

### Task 8: inotify Watcher + Ansible Templates

**Files:**
- Create: `roles/comfyui/templates/comfyui-watcher.sh.j2`
- Create: `roles/comfyui/templates/comfyui-watcher.service.j2`
- Create: `roles/comfyui/templates/comfyui-cli.yaml.j2`
- Modify: `roles/comfyui/handlers/main.yml`

- [ ] **Step 1: Create watcher script template**

`roles/comfyui/templates/comfyui-watcher.sh.j2`:
```bash
#!/bin/bash
# {{ ansible_managed }}
# inotify watcher for ComfyUI browser workflow changes
# Commits browser-initiated changes to git with attribution
set -euo pipefail

WATCH_DIR="{{ comfyui_workflows_dir }}"

if [ ! -d "$WATCH_DIR/.git" ]; then
    echo "Not a git repo: $WATCH_DIR" >&2
    exit 1
fi

cd "$WATCH_DIR"

inotifywait -m -r -e modify,create,delete,moved_to,moved_from \
  --exclude '\.git/' \
  --format '%w%f' "$WATCH_DIR" | while read -r file; do
    # Belt and suspenders: skip .git events
    [[ "$file" == *"/.git/"* ]] && continue
    # Background subprocess debounce: one pending commit at a time
    if ! [ -f /tmp/comfyui-watcher-pending ]; then
        touch /tmp/comfyui-watcher-pending
        (
            set -uo pipefail
            sleep 5
            rm -f /tmp/comfyui-watcher-pending
            # Skip if last CLI commit was recent (avoid double-committing)
            last_cli=$(git log -1 --author="{{ comfyui_cli_author_name }}" --format=%ct 2>/dev/null || echo 0)
            now=$(date +%s)
            if [ $((now - last_cli)) -lt 10 ]; then exit 0; fi
            cd "$WATCH_DIR" || { echo "Cannot cd to $WATCH_DIR" >&2; exit 1; }
            git add -A || { echo "git add failed" >&2; exit 1; }
            git diff --cached --quiet || \
              git -c user.name="Browser UI" -c user.email="browser@localhost" \
                commit -m "browser: modified workflows" || echo "git commit failed" >&2
        ) &
    fi
done
```

- [ ] **Step 2: Create systemd service template**

`roles/comfyui/templates/comfyui-watcher.service.j2`:
```ini
# {{ ansible_managed }}
[Unit]
Description=ComfyUI Workflow Watcher (inotify + git)
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User={{ workstation_pi_user }}
Group={{ workstation_pi_user }}
ExecStart=/opt/workstation/comfyui-watcher.sh
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=comfyui-watcher

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Create CLI config template**

`roles/comfyui/templates/comfyui-cli.yaml.j2`:
```yaml
# {{ ansible_managed }}
# comfyui-cli configuration
comfyui_url: "http://localhost:{{ comfyui_port }}"
workflows_dir: "{{ comfyui_workflows_dir }}"
git_enabled: {{ comfyui_git_enabled | lower }}
git_author_name: "{{ comfyui_cli_author_name }}"
git_author_email: "{{ comfyui_cli_author_email }}"
qdrant_url: "{{ comfyui_qdrant_url }}"
qdrant_api_key: "{{ qdrant_api_key | default('') }}"
qdrant_collection: "{{ comfyui_qdrant_collection }}"
litellm_url: "https://llm.{{ domain_name }}/v1"
litellm_api_key: "{{ litellm_api_key | default('') }}"
```

- [ ] **Step 4: Add watcher restart handler**

Append to `roles/comfyui/handlers/main.yml`:

```yaml

- name: Restart comfyui-watcher
  ansible.builtin.systemd:
    name: comfyui-watcher
    state: restarted
    daemon_reload: true
  become: true
  when: not (common_molecule_mode | default(false))
```

- [ ] **Step 5: Commit**

```bash
git add roles/comfyui/templates/comfyui-watcher.sh.j2 roles/comfyui/templates/comfyui-watcher.service.j2 roles/comfyui/templates/comfyui-cli.yaml.j2 roles/comfyui/handlers/main.yml
git commit -m "feat(comfyui): inotify watcher + systemd service + CLI config templates"
```

---

### Task 9: Ansible Tasks — CLI Install + Git Init + Watcher

**Files:**
- Modify: `roles/comfyui/tasks/main.yml` (append new tasks after existing content)

- [ ] **Step 1: Append new tasks to `tasks/main.yml`**

Add after line 169 (the `Display ComfyUI health status` task):

```yaml

# --- Concurrent Access: CLI + Git + Watcher ---

- name: Create user data directory for workflows
  ansible.builtin.file:
    path: "{{ comfyui_workflows_dir }}"
    state: directory
    owner: "1000"
    group: "1000"
    mode: "0755"
  become: true

- name: Create CLI install directory
  ansible.builtin.file:
    path: "{{ comfyui_cli_install_dir }}"
    state: directory
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0755"
  become: true

- name: Copy CLI source code
  ansible.builtin.copy:
    src: comfyui-cli/
    dest: "{{ comfyui_cli_install_dir }}/"
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0644"
  become: true
  register: _comfyui_cli_src

- name: Install CLI Python dependencies in venv
  ansible.builtin.pip:
    requirements: "{{ comfyui_cli_install_dir }}/requirements.txt"
    virtualenv: "{{ comfyui_cli_install_dir }}/.venv"
    virtualenv_command: "python3 -m venv"
  become: true
  become_user: "{{ workstation_pi_user }}"

- name: Install CLI package in venv (editable)
  ansible.builtin.shell:
    cmd: |
      set -euo pipefail
      {{ comfyui_cli_install_dir }}/.venv/bin/pip install -e "{{ comfyui_cli_install_dir }}"
    executable: /bin/bash
  become: true
  become_user: "{{ workstation_pi_user }}"
  register: _comfyui_cli_pip
  changed_when: "'Successfully installed' in _comfyui_cli_pip.stdout"

- name: Create CLI symlink in /usr/local/bin
  ansible.builtin.file:
    src: "{{ comfyui_cli_install_dir }}/.venv/bin/comfyui-cli"
    dest: /usr/local/bin/comfyui-cli
    state: link
  become: true

- name: Deploy CLI config
  ansible.builtin.template:
    src: comfyui-cli.yaml.j2
    dest: "/home/{{ workstation_pi_user }}/.comfyui-cli.yaml"
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0600"
  become: true

- name: Initialize git repo in workflows directory
  ansible.builtin.command:
    cmd: git init
    chdir: "{{ comfyui_workflows_dir }}"
    creates: "{{ comfyui_workflows_dir }}/.git"
  become: true
  become_user: "{{ workstation_pi_user }}"

- name: Create .gitignore in workflows repo
  ansible.builtin.copy:
    content: |
      *.tmp
      *.bak
      .DS_Store
      __pycache__/
      *.pyc
    dest: "{{ comfyui_workflows_dir }}/.gitignore"
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0644"
  become: true

- name: Add Gitea remote to workflows repo
  ansible.builtin.command:
    cmd: git remote add origin {{ comfyui_git_remote }}
    chdir: "{{ comfyui_workflows_dir }}"
  become: true
  become_user: "{{ workstation_pi_user }}"
  changed_when: false
  failed_when: false

- name: Initial git commit in workflows repo
  ansible.builtin.shell:
    cmd: |
      set -euo pipefail
      cd {{ comfyui_workflows_dir }}
      git add -A
      git diff --cached --quiet || git -c user.name="Ansible" -c user.email="ansible@localhost" commit -m "init: workflow repository"
      git push -u origin main 2>/dev/null || true
    executable: /bin/bash
  become: true
  become_user: "{{ workstation_pi_user }}"
  changed_when: false
  failed_when: false

- name: Install inotify-tools
  ansible.builtin.apt:
    name: inotify-tools
    state: present
  become: true

- name: Deploy watcher script
  ansible.builtin.template:
    src: comfyui-watcher.sh.j2
    dest: /opt/workstation/comfyui-watcher.sh
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0755"
  become: true
  notify: Restart comfyui-watcher

- name: Deploy watcher systemd service
  ansible.builtin.template:
    src: comfyui-watcher.service.j2
    dest: /etc/systemd/system/comfyui-watcher.service
    owner: root
    group: root
    mode: "0644"
  become: true
  notify: Restart comfyui-watcher

- name: Enable and start watcher service
  ansible.builtin.systemd:
    name: comfyui-watcher
    enabled: true
    state: started
    daemon_reload: true
  become: true
  when: not (common_molecule_mode | default(false))

- name: Set up git push cron job
  ansible.builtin.cron:
    name: "comfyui-workflows-git-push"
    minute: "*/{{ comfyui_git_push_interval }}"
    job: "cd {{ comfyui_workflows_dir }} && git push --quiet origin main 2>/dev/null || git push --quiet -u origin main 2>/dev/null || true"
    user: "{{ workstation_pi_user }}"
  become: true
```

- [ ] **Step 2: Verify lint passes**

```bash
source .venv/bin/activate && ansible-lint roles/comfyui/tasks/main.yml
```

Expected: 0 warnings/errors (or only pre-existing ones)

- [ ] **Step 3: Commit**

```bash
git add roles/comfyui/tasks/main.yml
git commit -m "feat(comfyui): Ansible tasks for CLI install, git init, watcher, cron"
```

---

## Phase 3: Advanced Execution (UI→API Conversion)

### Task 10: UI-to-API Format Converter

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/converter.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/test_converter.py`

- [ ] **Step 1: Create `converter.py`**

```python
"""Convert ComfyUI UI-format workflows to API-format for execution.

UI format: { "nodes": [...], "links": [...], "groups": [...] }
  - Each node has: id, type, widgets_values (positional), inputs (link slots)
  - Links: [link_id, origin_node_id, origin_slot, target_node_id, target_slot, type]

API format: { "node_id": { "class_type": "...", "inputs": { named_key: value } } }
  - Widget values mapped to named inputs via /object_info metadata
  - Links resolved to ["source_node_id_str", output_index]
"""
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


def is_api_format(workflow: Dict) -> bool:
    """Detect if workflow is already in API format."""
    if "nodes" in workflow and "links" in workflow:
        return False
    # API format: top-level keys are node IDs mapping to dicts with class_type
    for key, val in workflow.items():
        if isinstance(val, dict) and "class_type" in val:
            return True
    return False


def ui_to_api(workflow: Dict, object_info: Dict) -> Dict[str, Any]:
    """Convert UI-format workflow to API-format.

    Args:
        workflow: UI-format workflow JSON (has "nodes" and "links" keys)
        object_info: Response from GET /object_info (node class metadata)

    Returns:
        API-format workflow dict
    """
    nodes = workflow.get("nodes", [])
    links = workflow.get("links", [])

    # Build link lookup: link_id -> (origin_node_id, origin_slot_index)
    link_map = {}
    for link in links:
        # link = [link_id, origin_node_id, origin_slot, target_node_id, target_slot, type_name]
        if len(link) >= 4:
            link_id = link[0]
            origin_node_id = link[1]
            origin_slot = link[2]
            link_map[link_id] = (str(origin_node_id), origin_slot)

    api_workflow = {}

    for node in nodes:
        node_id = str(node["id"])
        class_type = node.get("type", "")

        # Skip reroute and other utility nodes
        if class_type in ("Reroute", "Note", "PrimitiveNode"):
            continue

        # Get input spec from object_info
        node_info = object_info.get(class_type, {})
        required_inputs = node_info.get("input", {}).get("required", {})
        optional_inputs = node_info.get("input", {}).get("optional", {})

        # Merge required + optional input specs (preserving order)
        all_input_specs = {}
        all_input_specs.update(required_inputs)
        all_input_specs.update(optional_inputs)

        # Build set of input names that are satisfied by links (not widgets)
        node_inputs = node.get("inputs", [])
        linked_input_names = {
            inp.get("name") for inp in node_inputs if inp.get("link") is not None
        }

        # Separate widget inputs (non-link) from link inputs
        widget_input_names = []
        for input_name, input_spec in all_input_specs.items():
            # Skip inputs that are connected via links — they are NOT widget values
            if input_name in linked_input_names:
                continue
            # Widget inputs have types like "INT", "FLOAT", "STRING", or combo lists
            if isinstance(input_spec, list) and len(input_spec) > 0:
                input_type = input_spec[0]
                if isinstance(input_type, str) and input_type.isupper():
                    # Primitive type → widget value
                    widget_input_names.append(input_name)
                elif isinstance(input_type, list):
                    # Combo/enum → widget value
                    widget_input_names.append(input_name)

        # Map widgets_values to named inputs
        widgets_values = node.get("widgets_values", [])
        inputs = {}

        widget_idx = 0
        for input_name in widget_input_names:
            if widget_idx < len(widgets_values):
                inputs[input_name] = widgets_values[widget_idx]
                widget_idx += 1

        # Map link connections from node.inputs
        for node_input in node_inputs:
            input_name = node_input.get("name", "")
            link_id = node_input.get("link")
            if link_id is not None and link_id in link_map:
                origin_node_id, origin_slot = link_map[link_id]
                inputs[input_name] = [origin_node_id, origin_slot]

        api_workflow[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
        }

        # Preserve _meta if present
        if "title" in node:
            api_workflow[node_id]["_meta"] = {"title": node["title"]}

    return api_workflow
```

- [ ] **Step 2: Write converter tests**

`tests/test_converter.py`:
```python
"""Tests for UI-to-API format converter."""
import pytest
from comfyui_cli.converter import is_api_format, ui_to_api


def test_is_api_format_detects_api():
    api_wf = {"3": {"class_type": "KSampler", "inputs": {}}}
    assert is_api_format(api_wf) is True


def test_is_api_format_detects_ui():
    ui_wf = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    assert is_api_format(ui_wf) is False


def test_ui_to_api_simple():
    """Simple workflow with one node and widget values."""
    ui_wf = {
        "nodes": [
            {
                "id": 5,
                "type": "EmptyLatentImage",
                "widgets_values": [512, 768, 1],
                "inputs": [],
            }
        ],
        "links": [],
    }
    object_info = {
        "EmptyLatentImage": {
            "input": {
                "required": {
                    "width": ["INT", {"default": 512}],
                    "height": ["INT", {"default": 512}],
                    "batch_size": ["INT", {"default": 1}],
                },
                "optional": {},
            }
        }
    }

    result = ui_to_api(ui_wf, object_info)
    assert "5" in result
    assert result["5"]["class_type"] == "EmptyLatentImage"
    assert result["5"]["inputs"]["width"] == 512
    assert result["5"]["inputs"]["height"] == 768
    assert result["5"]["inputs"]["batch_size"] == 1


def test_ui_to_api_with_links():
    """Workflow with linked nodes."""
    ui_wf = {
        "nodes": [
            {
                "id": 4,
                "type": "CheckpointLoaderSimple",
                "widgets_values": ["model.safetensors"],
                "inputs": [],
            },
            {
                "id": 6,
                "type": "CLIPTextEncode",
                "widgets_values": ["a cat"],
                "inputs": [{"name": "clip", "link": 1}],
            },
        ],
        "links": [
            [1, 4, 1, 6, 0, "CLIP"],  # link_id=1, from node 4 slot 1, to node 6 slot 0
        ],
    }
    object_info = {
        "CheckpointLoaderSimple": {
            "input": {
                "required": {"ckpt_name": [["model.safetensors"], {}]},
                "optional": {},
            }
        },
        "CLIPTextEncode": {
            "input": {
                "required": {
                    "text": ["STRING", {"default": ""}],
                    "clip": ["CLIP"],
                },
                "optional": {},
            }
        },
    }

    result = ui_to_api(ui_wf, object_info)
    assert result["6"]["inputs"]["text"] == "a cat"
    assert result["6"]["inputs"]["clip"] == ["4", 1]


def test_ui_to_api_skips_reroute():
    """Reroute nodes are excluded from API output."""
    ui_wf = {
        "nodes": [
            {"id": 1, "type": "Reroute", "widgets_values": [], "inputs": []},
            {"id": 2, "type": "Note", "widgets_values": ["hello"], "inputs": []},
        ],
        "links": [],
    }
    result = ui_to_api(ui_wf, {})
    assert len(result) == 0
```

- [ ] **Step 3: Run tests**

```bash
cd roles/comfyui/files/comfyui-cli && pytest tests/test_converter.py -v
```

Expected: 4 PASS

- [ ] **Step 4: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/converter.py roles/comfyui/files/comfyui-cli/tests/test_converter.py
git commit -m "feat(comfyui): UI-to-API workflow format converter with tests"
```

---

## Phase 4: Documentation Access (Qdrant)

### Task 11: Docs Command (Qdrant Search)

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/docs.py`

- [ ] **Step 1: Create `docs.py`**

```python
"""Documentation search command via Qdrant semantic search."""
import click

from .main import cli, pass_ctx


@cli.command("docs")
@click.argument("query")
@click.option("--limit", default=5, help="Max results")
@click.option("--category", default=None, help="Filter by category (e.g., built-in-nodes, api-reference)")
@pass_ctx
def docs(ctx, query, limit, category):
    """Search ComfyUI documentation via Qdrant."""
    qdrant_url = ctx.config.get("qdrant_url", "")
    qdrant_api_key = ctx.config.get("qdrant_api_key", "")
    collection = ctx.config.get("qdrant_collection", "comfyui-docs")
    litellm_url = ctx.config.get("litellm_url", "")
    litellm_api_key = ctx.config.get("litellm_api_key", "")

    if not qdrant_url or not litellm_url:
        ctx.error("Qdrant/LiteLLM not configured. Set qdrant_url and litellm_url in config.")

    try:
        from openai import OpenAI
        from qdrant_client import QdrantClient
        from urllib.parse import urlparse
    except ImportError:
        ctx.error("Install docs extras: pip install comfyui-cli[docs]")

    # Generate query embedding
    openai_client = OpenAI(base_url=litellm_url, api_key=litellm_api_key)
    try:
        embedding_resp = openai_client.embeddings.create(
            model="embedding",
            input=query[:8000],
        )
        query_vector = embedding_resp.data[0].embedding
    except Exception as e:
        ctx.error(f"Embedding generation failed: {e}")

    # Search Qdrant
    parsed = urlparse(qdrant_url)
    host = parsed.hostname or qdrant_url
    port = parsed.port or (443 if parsed.scheme == "https" else 6333)
    https = parsed.scheme == "https"

    qdrant = QdrantClient(host=host, port=port, api_key=qdrant_api_key, https=https)

    filter_condition = None
    if category:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        filter_condition = Filter(
            must=[FieldCondition(key="category", match=MatchValue(value=category))]
        )

    try:
        results = qdrant.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=limit,
            query_filter=filter_condition,
        )
    except Exception as e:
        ctx.error(f"Qdrant search failed: {e}")

    docs_results = [
        {
            "score": round(hit.score, 3),
            "title": hit.payload.get("title", ""),
            "url": hit.payload.get("url", ""),
            "category": hit.payload.get("category", ""),
            "text": hit.payload.get("text", "")[:500],
        }
        for hit in results
    ]

    def human(data):
        if not data:
            return "No results found."
        lines = []
        for i, r in enumerate(data, 1):
            lines.append(f"\n{i}. [{r['score']}] {r['title']}")
            lines.append(f"   {r['url']}")
            lines.append(f"   {r['text'][:200]}...")
        return "\n".join(lines)

    ctx.output(docs_results, human)
```

- [ ] **Step 2: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/docs.py
git commit -m "feat(comfyui): CLI docs command — Qdrant semantic search"
```

---

## Phase 5: MCP Wrapper

### Task 12: MCP Server

**Files:**
- Create: `roles/comfyui/files/comfyui-studio/mcp_server.py`
- Create: `roles/comfyui/files/comfyui-studio/requirements.txt`

- [ ] **Step 1: Create `mcp_server.py`**

```python
"""comfyui-studio MCP server.

Thin wrapper that calls comfyui-cli subprocess for each tool.
"""
import json
import subprocess
import sys
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

CLI_CMD = "comfyui-cli"

server = Server("comfyui-studio")


def _run_cli(*args: str) -> str:
    """Run comfyui-cli with --json and return stdout."""
    cmd = [CLI_CMD, "--json"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        return json.dumps({"error": error})
    return result.stdout


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="list_workflows",
            description="List all ComfyUI workflows",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_workflow",
            description="Read a workflow JSON by path",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Workflow file path"}},
                "required": ["path"],
            },
        ),
        Tool(
            name="save_workflow",
            description="Save a workflow JSON to a path",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path"},
                    "workflow_json": {"type": "string", "description": "Workflow JSON string"},
                },
                "required": ["path", "workflow_json"],
            },
        ),
        Tool(
            name="execute_workflow",
            description="Execute a saved workflow by path",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workflow path"},
                    "params": {"type": "object", "description": "Parameter overrides (key: value)"},
                    "wait": {"type": "boolean", "description": "Wait for completion", "default": True},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="generate_image",
            description="Generate an image from a text prompt",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text prompt"},
                    "width": {"type": "integer", "default": 512},
                    "height": {"type": "integer", "default": 512},
                    "seed": {"type": "integer", "description": "Random seed (optional)"},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="get_queue",
            description="Show current ComfyUI queue (running + pending)",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_history",
            description="Show execution history",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10}},
                "required": [],
            },
        ),
        Tool(
            name="get_output",
            description="Retrieve outputs for a completed prompt",
            inputSchema={
                "type": "object",
                "properties": {"prompt_id": {"type": "string"}},
                "required": ["prompt_id"],
            },
        ),
        Tool(
            name="get_versions",
            description="Show git version history for a workflow",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="get_status",
            description="Show ComfyUI system status",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_nodes",
            description="List available node classes or show details for one",
            inputSchema={
                "type": "object",
                "properties": {"node_class": {"type": "string", "description": "Specific node class (optional)"}},
                "required": [],
            },
        ),
        Tool(
            name="upload_image",
            description="Upload an image to ComfyUI input directory",
            inputSchema={
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        ),
        Tool(
            name="search_docs",
            description="Search ComfyUI documentation via semantic search (Qdrant)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 5},
                    "category": {"type": "string", "description": "Filter category (optional)"},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "list_workflows":
            output = _run_cli("workflows", "list")

        elif name == "get_workflow":
            output = _run_cli("workflows", "get", arguments["path"])

        elif name == "save_workflow":
            cmd = [CLI_CMD, "--json", "workflows", "save", arguments["path"], "--stdin"]
            result = subprocess.run(
                cmd, input=arguments["workflow_json"],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout if result.returncode == 0 else json.dumps({"error": result.stderr})

        elif name == "execute_workflow":
            args = ["exec", arguments["path"]]
            if arguments.get("wait", True):
                args.append("--wait")
            for k, v in arguments.get("params", {}).items():
                args.extend(["--param", f"{k}={json.dumps(v) if not isinstance(v, str) else v}"])
            output = _run_cli(*args)

        elif name == "generate_image":
            args = ["exec", "--prompt", arguments["prompt"], "--wait"]
            if "width" in arguments:
                args.extend(["--width", str(arguments["width"])])
            if "height" in arguments:
                args.extend(["--height", str(arguments["height"])])
            if "seed" in arguments:
                args.extend(["--seed", str(arguments["seed"])])
            output = _run_cli(*args)

        elif name == "get_queue":
            output = _run_cli("queue")

        elif name == "get_history":
            args = ["history"]
            if "limit" in arguments:
                args.extend(["--limit", str(arguments["limit"])])
            output = _run_cli(*args)

        elif name == "get_output":
            output = _run_cli("output", arguments["prompt_id"])

        elif name == "get_versions":
            args = ["versions", arguments["path"]]
            if "limit" in arguments:
                args.extend(["--limit", str(arguments["limit"])])
            output = _run_cli(*args)

        elif name == "get_status":
            output = _run_cli("status")

        elif name == "get_nodes":
            args = ["nodes"]
            if arguments.get("node_class"):
                args.append(arguments["node_class"])
            output = _run_cli(*args)

        elif name == "upload_image":
            output = _run_cli("upload", arguments["file_path"])

        elif name == "search_docs":
            args = ["docs", arguments["query"]]
            if "limit" in arguments:
                args.extend(["--limit", str(arguments["limit"])])
            if arguments.get("category"):
                args.extend(["--category", arguments["category"]])
            output = _run_cli(*args)

        else:
            output = json.dumps({"error": f"Unknown tool: {name}"})

    except subprocess.TimeoutExpired:
        output = json.dumps({"error": f"Tool '{name}' timed out after 300s"})
    except Exception as e:
        output = json.dumps({"error": str(e)})

    return [TextContent(type="text", text=output)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 2: Create MCP requirements.txt**

`roles/comfyui/files/comfyui-studio/requirements.txt`:
```
mcp>=1.0,<2
```

- [ ] **Step 3: Commit**

```bash
git add roles/comfyui/files/comfyui-studio/
git commit -m "feat(comfyui): MCP server wrapper (comfyui-studio)"
```

---

### Task 13: MCP Ansible Tasks + .claude.json Config

**Files:**
- Modify: `roles/comfyui/tasks/main.yml` (append MCP tasks)

- [ ] **Step 1: Append MCP tasks to `tasks/main.yml`**

Add at the end of the file:

```yaml

# --- MCP Server (comfyui-studio) ---

- name: Create MCP server directory
  ansible.builtin.file:
    path: "{{ comfyui_studio_install_dir }}"
    state: directory
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0755"
  become: true

- name: Copy MCP server source
  ansible.builtin.copy:
    src: comfyui-studio/
    dest: "{{ comfyui_studio_install_dir }}/"
    owner: "{{ workstation_pi_user }}"
    group: "{{ workstation_pi_user }}"
    mode: "0644"
  become: true

- name: Install MCP server dependencies in CLI venv
  ansible.builtin.pip:
    requirements: "{{ comfyui_studio_install_dir }}/requirements.txt"
    virtualenv: "{{ comfyui_cli_install_dir }}/.venv"
  become: true
  become_user: "{{ workstation_pi_user }}"
```

- [ ] **Step 2: Note for manual .claude.json update**

After deploy, update `/home/mobuone/.claude.json` `mcpServers` section:

Remove entries: `comfy-ui`, `comfy-pilot`

Add entry:
```json
"comfyui-studio": {
  "type": "stdio",
  "command": "/opt/workstation/comfyui-cli/.venv/bin/python3",
  "args": ["/opt/workstation/comfyui-studio/mcp_server.py"],
  "env": {}
}
```

This is done manually (not by Ansible) because `.claude.json` is a local workstation config file that may contain other user-specific MCP entries.

- [ ] **Step 3: Commit**

```bash
git add roles/comfyui/tasks/main.yml
git commit -m "feat(comfyui): Ansible tasks for MCP server install"
```

---

## Verification

### Task 14: Deploy + Smoke Test

This task is run manually after all code is committed.

- [ ] **Step 1: Run lint**

```bash
source .venv/bin/activate && make lint
```

Expected: PASS (no new errors)

- [ ] **Step 2: Run CLI unit tests**

```bash
cd roles/comfyui/files/comfyui-cli && pip install -e ".[docs]" -r requirements-dev.txt && pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 3: Deploy to Pi**

```bash
source .venv/bin/activate && make deploy-role ROLE=comfyui ENV=workstation
```

- [ ] **Step 4: Smoke test CLI on Pi**

```bash
# SSH to Pi or run locally
comfyui-cli status --json
comfyui-cli workflows list --json
comfyui-cli queue --json
comfyui-cli nodes --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} node classes')"
```

Expected: All commands return valid JSON

- [ ] **Step 5: Smoke test volume mount**

Save a workflow in the browser UI at `studio.ewutelo.cloud`, then:

```bash
comfyui-cli workflows list --json
```

Expected: The saved workflow appears in the list

- [ ] **Step 6: Smoke test git versioning**

```bash
# Save a workflow via CLI
echo '{"nodes":[],"links":[]}' | comfyui-cli workflows save test-cli.json --stdin
comfyui-cli versions test-cli.json --json
```

Expected: Version history shows "cli: save test-cli.json" commit

- [ ] **Step 7: Smoke test watcher**

Save a workflow in the browser, wait 10 seconds, then:

```bash
cd /opt/workstation/data/comfyui/user/default/workflows && git log --oneline -5
```

Expected: "browser: modified workflows" commit appears

- [ ] **Step 8: Update .claude.json and test MCP**

Update `.claude.json` as described in Task 13 Step 2. Restart Claude Code, then test:

```
Use the comfyui-studio MCP to list workflows
```

Expected: MCP `list_workflows` tool returns workflow list

- [ ] **Step 9: Smoke test docs search**

```bash
comfyui-cli docs "KSampler parameters" --json
```

Expected: Returns Qdrant search results (requires `scripts/index-comfyui-docs.py` to have been run)

- [ ] **Step 10: Final commit**

```bash
git add -A && git status
```

If there are any remaining changes (e.g., from test artifacts), clean up and commit.
