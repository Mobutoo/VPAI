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

    def error(self, msg: str, exit_code: int = 1) -> None:
        """Print error and exit (raises SystemExit)."""
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
