"""Execution commands: exec, queue, cancel, history, output."""
import json
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
                return
        except Exception:
            ctx.error("Cannot list models. Is ComfyUI running?")
            return

    elif workflow_path:
        # Load workflow from file or API
        try:
            workflow_data = ctx.client.get_workflow(workflow_path)
        except Exception as e:
            ctx.error(f"Cannot load workflow '{workflow_path}': {e}")
            return

        # Detect format: UI format has 'nodes'+'links', API format has class_type values
        from .converter import is_api_format, ui_to_api
        if not is_api_format(workflow_data):
            try:
                object_info = ctx.client.get_object_info()
                api_workflow = ui_to_api(workflow_data, object_info)
            except Exception as e:
                ctx.error(f"UI->API conversion failed: {e}")
                return
        else:
            api_workflow = workflow_data

        # Apply --param overrides
        for p in param:
            if "=" not in p:
                ctx.error(f"Invalid param format '{p}', use key=value (e.g., 3.inputs.seed=42)")
                return
            key, val = p.split("=", 1)
            parts = key.split(".")
            target = api_workflow
            for part in parts[:-1]:
                if part not in target:
                    ctx.error(f"Invalid param path '{key}': '{part}' not found")
                    return
                target = target[part]
            try:
                target[parts[-1]] = json.loads(val)
            except json.JSONDecodeError:
                target[parts[-1]] = val
    else:
        ctx.error("Provide a workflow path or --prompt")
        return

    # Submit
    try:
        result = ctx.client.queue_prompt(api_workflow)
        prompt_id = result.get("prompt_id", "unknown")
    except Exception as e:
        ctx.error(f"Execution failed: {e}")
        return

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
        return

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
            return
    except Exception as e:
        ctx.error(str(e))
        return
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
        return

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
        return

    if not entry:
        ctx.error(f"No output found for {prompt_id}")
        return

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
