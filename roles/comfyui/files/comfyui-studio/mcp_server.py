"""comfyui-studio MCP server.

Thin wrapper that calls comfyui-cli subprocess for each tool.
"""
import json
import subprocess
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

CLI_CMD = "/usr/local/bin/comfyui-cli"

# Montage bridge modules (direct import, not subprocess — complex JSON I/O)
import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "comfyui-cli"))
from comfyui_cli.config import load_config
from comfyui_cli.montage import MontageBuilder, montage_diff
from comfyui_cli.montage_render import MontageRenderer
from comfyui_cli.montage_agent import MontageAgent

_config = load_config()
_montage_builder = MontageBuilder()
_montage_renderer = MontageRenderer(
    api_url=_config.get("remotion_api_url", "http://localhost:3200"),
    api_token=_config.get("remotion_api_token") or None,
)
_montage_agent = MontageAgent(
    litellm_url=_config.get("litellm_url", ""),
    litellm_api_key=_config.get("litellm_api_key", ""),
    model=_config.get("montage_adjust_model", "qwen/qwen3-coder"),
) if _config.get("litellm_url") else None

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
        Tool(
            name="montage_build",
            description="Assemble assets into a MontageProps JSON ready for Remotion render",
            inputSchema={
                "type": "object",
                "properties": {
                    "assets": {
                        "type": "array", "items": {"type": "string"},
                        "description": "List of asset URLs (images or videos)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["reel_9_16", "landscape_16_9", "square_1_1"],
                        "description": "Output format",
                    },
                    "pacing": {
                        "type": "string", "enum": ["fast", "medium", "slow"],
                        "description": "Pacing preset",
                    },
                    "title": {"type": "string", "description": "Optional title card text"},
                    "brand_style": {
                        "type": "object",
                        "description": "Optional brand style (palette, typography, tone)",
                    },
                },
                "required": ["assets", "format", "pacing"],
            },
        ),
        Tool(
            name="montage_render",
            description="Send MontageProps to Remotion and return render result (MP4)",
            inputSchema={
                "type": "object",
                "properties": {
                    "montage_props": {
                        "type": "object", "description": "MontageProps JSON",
                    },
                    "quality": {
                        "type": "string", "enum": ["draft", "final"],
                        "description": "Render quality: draft (720p) or final (1080p). Default: draft",
                        "default": "draft",
                    },
                },
                "required": ["montage_props"],
            },
        ),
        Tool(
            name="montage_adjust",
            description="Modify a MontageProps via natural language instruction (uses LLM)",
            inputSchema={
                "type": "object",
                "properties": {
                    "montage_props": {
                        "type": "object", "description": "Current MontageProps JSON",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Natural language edit instruction",
                    },
                },
                "required": ["montage_props", "instruction"],
            },
        ),
        Tool(
            name="montage_diff",
            description="Compare two MontageProps and return a readable list of changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "before": {"type": "object", "description": "Original MontageProps"},
                    "after": {"type": "object", "description": "Modified MontageProps"},
                },
                "required": ["before", "after"],
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
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                output = json.dumps({"error": error})
            else:
                output = result.stdout

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

        elif name == "montage_build":
            props = _montage_builder.build(
                assets=arguments["assets"],
                format=arguments["format"],
                pacing=arguments["pacing"],
                title=arguments.get("title"),
                brand_style=arguments.get("brand_style"),
            )
            output = json.dumps(props)

        elif name == "montage_render":
            props = arguments["montage_props"]
            quality = arguments.get("quality", "draft")
            if quality == "draft":
                props = {**props, "width": min(props.get("width", 1080), 1280),
                         "height": min(props.get("height", 1920), 1280)}
            result = _montage_renderer.render(props)
            output = json.dumps(result)

        elif name == "montage_adjust":
            if _montage_agent is None:
                output = json.dumps(
                    {"error": "LiteLLM not configured — set litellm_url in config"})
            else:
                result = _montage_agent.adjust(
                    montage_props=arguments["montage_props"],
                    instruction=arguments["instruction"],
                )
                output = json.dumps(result)

        elif name == "montage_diff":
            result = montage_diff(arguments["before"], arguments["after"])
            output = json.dumps(result)

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
