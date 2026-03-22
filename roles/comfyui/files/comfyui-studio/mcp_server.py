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
