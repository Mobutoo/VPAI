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
