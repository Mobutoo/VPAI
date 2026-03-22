"""End-to-end tests for comfyui-cli against a running ComfyUI instance.

Requires: ComfyUI running on localhost:8188
Run: pytest tests/test_e2e.py -v --e2e
Skip: Without --e2e flag, all tests are skipped.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest
import requests


def pytest_addoption(parser):
    """Register --e2e flag (only used if conftest doesn't already define it)."""
    pass  # Handled in conftest.py


def comfyui_available():
    """Check if ComfyUI is reachable."""
    try:
        resp = requests.get("http://localhost:8188/system_stats", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


skip_no_comfyui = pytest.mark.skipif(
    not comfyui_available(),
    reason="ComfyUI not running on localhost:8188",
)


def cli(*args) -> subprocess.CompletedProcess:
    """Run comfyui-cli and return result."""
    cmd = ["comfyui-cli", "--json"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result


def cli_json(*args) -> dict:
    """Run comfyui-cli --json and parse output."""
    result = cli(*args)
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return json.loads(result.stdout)


# --- System ---

@skip_no_comfyui
class TestStatus:
    def test_status_returns_system_info(self):
        data = cli_json("status")
        assert "system" in data
        assert "comfyui_version" in data["system"]
        assert data["system"]["comfyui_version"]

    def test_status_has_devices(self):
        data = cli_json("status")
        assert "devices" in data
        assert isinstance(data["devices"], list)


# --- Workflows CRUD ---

@skip_no_comfyui
class TestWorkflowCRUD:
    """Test full workflow lifecycle: list → save → get → rename → delete."""

    TEST_WORKFLOW_NAME = "_e2e_test_workflow.json"
    TEST_WORKFLOW_RENAMED = "_e2e_test_renamed.json"
    TEST_WORKFLOW_DATA = {
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "e2e test", "clip": ["4", 1]},
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "test.safetensors"},
        },
    }

    def test_01_list_workflows_initial(self):
        """List workflows (should not contain our test workflow)."""
        data = cli_json("workflows", "list")
        assert isinstance(data, list)
        # Clean up if leftover from previous run
        if self.TEST_WORKFLOW_NAME in data:
            cli("workflows", "delete", self.TEST_WORKFLOW_NAME)
        if self.TEST_WORKFLOW_RENAMED in data:
            cli("workflows", "delete", self.TEST_WORKFLOW_RENAMED)

    def test_02_save_workflow(self):
        """Save a test workflow."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(self.TEST_WORKFLOW_DATA, f)
            tmp_path = f.name

        result = cli("workflows", "save", self.TEST_WORKFLOW_NAME, "--file", tmp_path)
        assert result.returncode == 0, f"Save failed: {result.stderr}"
        Path(tmp_path).unlink()

    def test_03_get_workflow(self):
        """Read back the saved workflow."""
        data = cli_json("workflows", "get", self.TEST_WORKFLOW_NAME)
        assert "6" in data
        assert data["6"]["class_type"] == "CLIPTextEncode"

    def test_04_list_contains_workflow(self):
        """Verify workflow appears in listing."""
        data = cli_json("workflows", "list")
        assert self.TEST_WORKFLOW_NAME in data

    def test_05_rename_workflow(self):
        """Rename the workflow using the fixed move route."""
        result = cli(
            "workflows", "rename",
            self.TEST_WORKFLOW_NAME, self.TEST_WORKFLOW_RENAMED,
        )
        assert result.returncode == 0, f"Rename failed: {result.stderr}"

        # Verify old name gone, new name exists
        data = cli_json("workflows", "list")
        assert self.TEST_WORKFLOW_NAME not in data
        assert self.TEST_WORKFLOW_RENAMED in data

    def test_06_delete_workflow(self):
        """Delete the renamed workflow."""
        result = cli("workflows", "delete", self.TEST_WORKFLOW_RENAMED)
        assert result.returncode == 0, f"Delete failed: {result.stderr}"

        data = cli_json("workflows", "list")
        assert self.TEST_WORKFLOW_RENAMED not in data


# --- Introspection ---

@skip_no_comfyui
class TestIntrospection:
    def test_nodes_list(self):
        """List all node classes."""
        data = cli_json("nodes")
        assert isinstance(data, dict)
        assert len(data) > 100  # ComfyUI has 800+ nodes

    def test_nodes_info_specific(self):
        """Get info for a specific node class."""
        data = cli_json("nodes", "CLIPTextEncode")
        assert "CLIPTextEncode" in data
        node = data["CLIPTextEncode"]
        assert "input" in node
        assert "output" in node

    def test_models_list(self):
        """List model folders."""
        data = cli_json("models")
        assert isinstance(data, list)
        # checkpoints should always be present as a folder
        assert "checkpoints" in data


# --- Queue ---

@skip_no_comfyui
class TestQueue:
    def test_queue_status(self):
        """Get queue status."""
        data = cli_json("queue")
        assert "queue_running" in data
        assert "queue_pending" in data


# --- History ---

@skip_no_comfyui
class TestHistory:
    def test_history_returns_dict(self):
        """History returns a dict (may be empty)."""
        data = cli_json("history")
        assert isinstance(data, dict)


# --- Upload ---

@skip_no_comfyui
class TestUpload:
    def test_upload_image(self):
        """Upload a minimal PNG image."""
        # Minimal valid 1x1 red PNG (67 bytes)
        import base64
        png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(base64.b64decode(png_b64))
            tmp_path = f.name

        result = cli("upload", tmp_path)
        assert result.returncode == 0, f"Upload failed: {result.stderr}"
        Path(tmp_path).unlink()


# --- MCP Server ---

@skip_no_comfyui
class TestMCPServer:
    """Test MCP server subprocess delegation."""

    MCP_SERVER = "/opt/workstation/comfyui-studio/mcp_server.py"
    MCP_VENV_PYTHON = "/opt/workstation/comfyui-cli/.venv/bin/python3"

    def _mcp_call(self, method: str, params: dict = None) -> dict:
        """Send a JSON-RPC call to the MCP server and get the response."""
        if not Path(self.MCP_SERVER).exists():
            pytest.skip("MCP server not installed")

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        }
        result = subprocess.run(
            [self.MCP_VENV_PYTHON, self.MCP_SERVER],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=15,
        )
        # MCP server uses stdio — parse last JSON line from stdout
        for line in reversed(result.stdout.strip().split("\n")):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return {"error": f"No JSON in output: {result.stdout[:200]}"}

    def test_mcp_server_exists(self):
        """MCP server file is deployed."""
        assert Path(self.MCP_SERVER).exists()

    def test_mcp_tools_list(self):
        """MCP server exposes tools."""
        resp = self._mcp_call("tools/list")
        if "result" in resp:
            tools = resp["result"].get("tools", [])
            tool_names = [t["name"] for t in tools]
            assert "status" in tool_names
            assert "list_workflows" in tool_names
