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
        return

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
        return

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
