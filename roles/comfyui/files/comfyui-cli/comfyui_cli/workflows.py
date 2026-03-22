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
        return

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
        return

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
        return

    try:
        ctx.client.save_workflow(path, data)
    except Exception as e:
        ctx.error(f"Cannot save '{path}': {e}")
        return

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
        return

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
        return

    if ctx.config.get("git_enabled"):
        from .git_ops import git_commit
        git_commit(ctx.config, f"cli: rename {old_path} -> {new_path}", [old_path, new_path])

    ctx.output(
        {"status": "renamed", "old": old_path, "new": new_path},
        lambda d: f"Renamed: {d['old']} -> {d['new']}",
    )
