"""VideoRef Engine v0.7.0 -- Multi-scene video analysis + 14-step production pipeline."""
import os
import re
import json
import asyncio
import base64
import hashlib
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

# --- Configuration from env (immutable after startup) ---
WATCH_DIR = Path(os.environ.get("WATCH_DIR", "/watch"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/analyzed"))
COMFYUI_DIR = Path(os.environ.get("COMFYUI_WORKFLOWS_DIR", "/comfyui-workflows"))
LITELLM_URL = os.environ.get("LITELLM_URL", "")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
GITEA_URL = os.environ.get("GITEA_URL", "")
GITEA_TOKEN = os.environ.get("GITEA_TOKEN", "")
KITSU_URL = os.environ.get("KITSU_URL", "")
KITSU_TOKEN = os.environ.get("KITSU_TOKEN", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "videoref_styles")
N8N_CREATIVE_PIPELINE_URL = os.environ.get("N8N_CREATIVE_PIPELINE_URL", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_TOPIC_ID = os.environ.get("TELEGRAM_TOPIC_ID", "")

COMFYUI_API_URL = os.environ.get("COMFYUI_API_URL", "http://workstation_comfyui:8188")
FAL_API_KEY = os.environ.get("FAL_API_KEY", "")
BYTEPLUS_API_KEY = os.environ.get("BYTEPLUS_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
REMOTION_URL = os.environ.get("REMOTION_URL", "")
CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "/usr/local/bin/claude")
MODEL_REGISTRY_COLLECTION = "model-registry"
CREATIVE_ASSETS_DIR = Path("/app/creative-assets")

VERSION = "0.11.0"
SCENE_THRESHOLD = 0.3
SHORT_VIDEO_SECONDS = 30
JOBS_DIR = OUTPUT_DIR / "jobs"

# --- Camera presets cache (loaded once from Gitea) ---
_camera_presets_cache: dict[str, Any] | None = None


# ============================================================
# Pipeline State Machine — 14 production steps
# ============================================================
PIPELINE_STEPS = [
    {"id": "brief", "task_type": "Brief", "needs_human": False, "optional": False, "kitsu_status": "done"},
    {"id": "research", "task_type": "Recherche", "needs_human": False, "optional": False, "kitsu_status": "done"},
    {"id": "script", "task_type": "Script", "needs_human": False, "optional": False, "kitsu_status": "done"},
    {"id": "storyboard", "task_type": "Storyboard CF", "needs_human": True, "optional": False, "kitsu_status": "wfa"},
    {"id": "voiceover", "task_type": "Voice-over", "needs_human": False, "optional": True, "kitsu_status": "done"},
    {"id": "music", "task_type": "Music", "needs_human": False, "optional": True, "kitsu_status": "done"},
    {"id": "imagegen", "task_type": "Image Gen", "needs_human": True, "optional": False, "kitsu_status": "wfa"},
    {"id": "videogen", "task_type": "Video Gen", "needs_human": True, "optional": False, "kitsu_status": "wfa"},
    {"id": "montage", "task_type": "Montage", "needs_human": True, "optional": False, "kitsu_status": "wfa"},
    {"id": "subtitles", "task_type": "Sous-titres", "needs_human": False, "optional": True, "kitsu_status": "done"},
    {"id": "colorgrade", "task_type": "Color Grade", "needs_human": True, "optional": False, "kitsu_status": "wfa"},
    {"id": "review", "task_type": "Review", "needs_human": True, "optional": False, "kitsu_status": "wfa"},
    {"id": "export", "task_type": "Export", "needs_human": False, "optional": False, "kitsu_status": "done"},
    {"id": "publish", "task_type": "Publication", "needs_human": False, "optional": True, "kitsu_status": "done"},
]

STEP_IDS = [s["id"] for s in PIPELINE_STEPS]
STEP_MAP = {s["id"]: s for s in PIPELINE_STEPS}


# ============================================================
# 1. Video probing helpers
# ============================================================
def _get_duration(video_path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 30.0


async def _get_video_info(video_path: Path) -> dict[str, Any]:
    """Get fps, dimensions, and duration from a video."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,width,height",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    try:
        data = json.loads(stdout)
        stream = data.get("streams", [{}])[0]
        fps_str = stream.get("avg_frame_rate", "30/1")
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) > 0 else 30.0
        duration = float(data.get("format", {}).get("duration", 0))
        return {
            "fps": round(fps, 2),
            "width": stream.get("width", 0),
            "height": stream.get("height", 0),
            "duration_s": round(duration, 2),
        }
    except (KeyError, IndexError, ValueError, ZeroDivisionError):
        return {"fps": 30.0, "width": 0, "height": 0, "duration_s": _get_duration(video_path)}


# ============================================================
# 2. Scene segmentation via ffmpeg
# ============================================================
async def detect_scenes(video_path: Path) -> list[dict[str, float]]:
    """Detect scene boundaries using ffmpeg scene filter.

    Returns list of dicts with 'start' and 'end' timestamps (seconds).
    Short videos (<30s) with no scene changes return a single scene.
    """
    duration = _get_duration(video_path)
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-filter_complex",
        f"select='gt(scene,{SCENE_THRESHOLD})',metadata=print:file=-",
        "-f", "null", "-",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()

    timestamps = _parse_scene_timestamps(stdout.decode(errors="replace"))

    if not timestamps:
        return [{"start": 0.0, "end": duration}]

    scenes: list[dict[str, float]] = []
    prev = 0.0
    for ts in timestamps:
        if ts > prev:
            scenes.append({"start": round(prev, 3), "end": round(ts, 3)})
        prev = ts
    if prev < duration:
        scenes.append({"start": round(prev, 3), "end": round(duration, 3)})
    return scenes if scenes else [{"start": 0.0, "end": duration}]


def _parse_scene_timestamps(output: str) -> list[float]:
    """Parse pts_time values from ffmpeg metadata output."""
    timestamps: list[float] = []
    for line in output.splitlines():
        match = re.search(r"pts_time:([0-9.]+)", line)
        if match:
            try:
                timestamps.append(float(match.group(1)))
            except ValueError:
                continue
    return sorted(set(timestamps))


# ============================================================
# 3. Keyframe extraction (1 per scene at midpoint)
# ============================================================
async def extract_keyframe_at(video_path: Path, timestamp: float, out_path: Path) -> bool:
    """Extract a single keyframe at a specific timestamp."""
    cmd = [
        "ffmpeg", "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_path),
        "-y",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return out_path.exists()


async def extract_scene_keyframes(
    video_path: Path, scenes: list[dict[str, float]]
) -> list[Path]:
    """Extract 1 keyframe per scene at the midpoint. Returns list of frame paths."""
    tmpdir = Path(tempfile.mkdtemp(prefix="vref_kf_"))
    frames: list[Path] = []
    for idx, scene in enumerate(scenes):
        midpoint = (scene["start"] + scene["end"]) / 2.0
        out_path = tmpdir / f"scene_{idx:03d}.jpg"
        ok = await extract_keyframe_at(video_path, midpoint, out_path)
        if ok:
            frames.append(out_path)
    # Fallback: if no frames extracted, grab frame at 1s
    if not frames:
        fallback = tmpdir / "fallback_000.jpg"
        await extract_keyframe_at(video_path, 1.0, fallback)
        if fallback.exists():
            frames.append(fallback)
    return frames


# ============================================================
# 4. Color palette extraction (k-means via numpy)
# ============================================================
async def extract_colors(frame_path: Path, n_colors: int = 5) -> list[str]:
    """Extract dominant colors from a frame using numpy k-means."""
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(frame_path).resize((150, 150)).convert("RGB")
        pixels = np.array(img).reshape(-1, 3).astype(np.float32)

        rng = np.random.default_rng(42)
        centers = pixels[rng.choice(len(pixels), n_colors, replace=False)]
        for _ in range(3):
            dists = np.linalg.norm(pixels[:, None] - centers[None], axis=2)
            labels = dists.argmin(axis=1)
            for k in range(n_colors):
                mask = labels == k
                if mask.any():
                    centers[k] = pixels[mask].mean(axis=0)

        _, counts = np.unique(
            np.linalg.norm(pixels[:, None] - centers[None], axis=2).argmin(axis=1),
            return_counts=True,
        )
        order = np.argsort(-counts)
        return [
            "#{:02x}{:02x}{:02x}".format(*centers[i].astype(int))
            for i in order
        ]
    except ImportError:
        return []


# ============================================================
# 5. Motion estimation
# ============================================================
def estimate_motion(info: dict[str, Any]) -> dict[str, Any]:
    """Estimate motion from video info. Pure function, no I/O."""
    fps = info.get("fps", 30.0)
    duration = info.get("duration_s", 30.0)
    score = min(1.0, fps / 60.0) * min(1.0, 30.0 / max(1.0, duration))
    if score > 0.6:
        level = "high"
    elif score > 0.3:
        level = "medium"
    else:
        level = "low"
    return {"motion_level": level, "motion_score": round(score, 3)}


# ============================================================
# 6. Claude Vision analysis via LiteLLM
# ============================================================
async def _call_litellm(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a chat completion request to LiteLLM. Returns parsed JSON or raw."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LITELLM_URL}/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {LITELLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                return {"error": f"LiteLLM {resp.status}: {body[:200]}"}
            data = await resp.json()
            content = data["choices"][0]["message"]["content"]
            try:
                start = content.index("{")
                end = content.rindex("}") + 1
                return json.loads(content[start:end])
            except (ValueError, json.JSONDecodeError):
                return {"raw_analysis": content}


async def _call_litellm_text(prompt: str) -> str:
    """Call LiteLLM and return raw text response."""
    if not LITELLM_URL or not LITELLM_API_KEY:
        return ""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LITELLM_URL}/v1/chat/completions",
            json={
                "model": "claude-sonnet",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
            },
            headers={
                "Authorization": f"Bearer {LITELLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                return ""
            data = await resp.json()
            return data["choices"][0]["message"]["content"].strip()


def _encode_frame(frame_path: Path) -> dict[str, Any]:
    """Encode a frame as a base64 image_url content block."""
    b64 = base64.b64encode(frame_path.read_bytes()).decode()
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
    }


async def analyze_scene(
    frame: Path, scene_idx: int, colors: list[str], motion: dict[str, Any],
) -> dict[str, Any]:
    """Analyze a single scene keyframe with Claude Vision."""
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"error": "LITELLM not configured"}

    prompt = (
        f"Analyze this video keyframe (scene {scene_idx + 1}). "
        f"Detected colors: {', '.join(colors[:5])}. "
        f"Motion: {motion.get('motion_level', 'unknown')}. "
        "Return JSON with: "
        '{"style": "...", "mood": "...", "lighting": "...", '
        '"composition": "...", "color_grade": "...", '
        '"key_elements": ["..."], '
        '"suggested_prompt": "...", "negative_prompt": "..."}'
    )
    payload = {
        "model": "claude-sonnet",
        "messages": [{
            "role": "user",
            "content": [_encode_frame(frame), {"type": "text", "text": prompt}],
        }],
        "max_tokens": 1024,
    }
    try:
        return await _call_litellm(payload)
    except Exception as exc:
        return {"error": str(exc)}


async def synthesize_video(
    scene_analyses: list[dict[str, Any]], filename: str, info: dict[str, Any],
) -> dict[str, Any]:
    """Synthesize a whole-video summary from per-scene analyses."""
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"error": "LITELLM not configured"}

    scenes_text = "\n".join(
        f"Scene {i+1}: style={s.get('style','?')}, mood={s.get('mood','?')}, "
        f"lighting={s.get('lighting','?')}, composition={s.get('composition','?')}"
        for i, s in enumerate(scene_analyses) if "error" not in s
    )
    prompt = (
        f"You are analyzing a video '{filename}' "
        f"({info.get('duration_s', '?')}s, {len(scene_analyses)} scenes). "
        f"Per-scene analyses:\n{scenes_text}\n\n"
        "Synthesize an overall video summary. Return JSON with: "
        '{"overall_style": "...", "narrative_arc": "...", '
        '"dominant_mood": "...", "visual_coherence": "high|medium|low", '
        '"suggested_prompt": "...", "negative_prompt": "..."}'
    )
    payload = {
        "model": "claude-sonnet",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }
    try:
        return await _call_litellm(payload)
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# 7. ComfyUI workflow generation
# ============================================================
async def fetch_template(template_name: str = "default") -> dict | None:
    """Fetch a ComfyUI workflow template from Gitea."""
    if not GITEA_URL or not GITEA_TOKEN:
        return None
    url = (
        f"{GITEA_URL}/api/v1/repos/mobuone/comfyui-templates"
        f"/raw/{template_name}.json?ref=main"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"token {GITEA_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                return await resp.json() if resp.status == 200 else None
    except Exception:
        return None


def _replace_in_tree(obj: Any, old: str, new: str) -> Any:
    """Recursively replace string values in a dict/list. Returns new structure."""
    if isinstance(obj, dict):
        return {
            k: (v.replace(old, new) if isinstance(v, str) and old in v
                else _replace_in_tree(v, old, new))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            (v.replace(old, new) if isinstance(v, str) and old in v
             else _replace_in_tree(v, old, new))
            for v in obj
        ]
    return obj


def generate_workflow(
    template: dict | None, synthesis: dict[str, Any], colors: list[str],
) -> dict[str, Any]:
    """Generate a ComfyUI workflow JSON from template + synthesis analysis."""
    prompt = synthesis.get("suggested_prompt", "beautiful scene, high quality")
    negative = synthesis.get("negative_prompt", "blurry, low quality")
    style = synthesis.get("overall_style", synthesis.get("style", "cinematic"))

    if template:
        wf = _replace_in_tree(template, "{{PROMPT}}", prompt)
        wf = _replace_in_tree(wf, "{{NEGATIVE}}", negative)
        wf = _replace_in_tree(wf, "{{STYLE}}", style)
        return wf

    return _build_fallback_workflow(prompt, negative, style, colors, synthesis)


def _build_fallback_workflow(
    prompt: str, negative: str, style: str,
    colors: list[str], analysis: dict[str, Any],
) -> dict[str, Any]:
    """Build minimal txt2img ComfyUI workflow as fallback."""
    return {
        "prompt": {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler_ancestral", "scheduler": "normal",
                    "denoise": 1.0, "model": ["4", 0],
                    "positive": ["6", 0], "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": f"{prompt}, {style} style", "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["4", 1]},
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "videoref", "images": ["8", 0]}},
        },
        "_metadata": {"source": "videoref-engine", "colors": colors[:5], "analysis": analysis},
    }


# ============================================================
# 8. Kitsu API helper
# ============================================================
async def _kitsu_api(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    json_body: dict | None = None,
    data: aiohttp.FormData | None = None,
) -> dict[str, Any] | list | None:
    """Call Kitsu/Zou API. Handles empty response bodies (DELETE)."""
    headers = {"Authorization": f"Bearer {KITSU_TOKEN}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"

    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=30),
    }
    if json_body is not None:
        kwargs["json"] = json_body
    if data is not None:
        kwargs["data"] = data
        kwargs["headers"] = {"Authorization": f"Bearer {KITSU_TOKEN}"}

    url = f"{KITSU_URL}/api{path}"
    async with session.request(method, url, **kwargs) as resp:
        if resp.status not in (200, 201, 204):
            body = await resp.text()
            raise RuntimeError(f"Kitsu {method} {path}: {resp.status} {body[:300]}")
        text = await resp.text()
        if not text.strip():
            return None
        return json.loads(text)


# ============================================================
# 9. Kitsu integration (Sequence + Shots + Tasks + Previews)
# ============================================================
async def _kitsu_get_project(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Get the first Kitsu project with its first episode."""
    projects = await _kitsu_api(session, "GET", "/data/projects")
    if not projects:
        raise RuntimeError("No projects in Kitsu")
    return projects[0]


async def _kitsu_get_asset_library(
    session: aiohttp.ClientSession,
) -> dict[str, Any]:
    """Get or create the global Asset Library project.

    MeTube auto-analyze creates assets here (not in a specific production).
    Productions can then cast assets from the library into their shots.
    """
    projects = await _kitsu_api(session, "GET", "/data/projects")
    library = next(
        (p for p in projects if p.get("production_type") == "assets"),
        None,
    )
    if library:
        return library

    # Create Asset Library if it doesn't exist
    statuses = await _kitsu_api(session, "GET", "/data/project-status")
    open_status = next(
        (s for s in statuses if s["name"].lower() == "open"), statuses[0]
    )
    library = await _kitsu_api(
        session, "POST", "/data/projects",
        json_body={
            "name": "Asset Library",
            "production_type": "assets",
            "project_status_id": open_status["id"],
        },
    )
    return library


async def _kitsu_create_project(
    session: aiohttp.ClientSession,
    title: str,
    production_type: str = "tvshow",
) -> dict[str, Any]:
    """Create a new Kitsu project (production) for a job.

    Each vref produce-start creates its own project so it appears
    as a separate production in the Kitsu UI.
    Uses 'tvshow' (not 'short') so assets + shots + concepts all work.
    production_type: 'short', 'tvshow', 'featurefilm', 'shots', 'assets'
    """
    # Get Open status
    statuses = await _kitsu_api(session, "GET", "/data/project-status")
    open_status = next(
        (s for s in statuses if s["name"].lower() == "open"), statuses[0]
    )

    project = await _kitsu_api(
        session, "POST", "/data/projects",
        json_body={
            "name": title,
            "production_type": production_type,
            "project_status_id": open_status["id"],
            "fps": "24",
            "resolution": "1920x1080",
            "production_style": "2d3d",
        },
    )

    # Associate ALL task types with the new project (not just ours)
    # This ensures any task type can be used, matching Paul Taff config
    all_types = await _kitsu_api(session, "GET", "/data/task-types")
    for tt in all_types:
        try:
            await _kitsu_api(
                session, "POST",
                f"/data/projects/{project['id']}/settings/task-types",
                json_body={"task_type_id": tt["id"]},
            )
        except Exception:
            pass  # May already be associated

    # Associate all task statuses
    all_statuses = await _kitsu_api(session, "GET", "/data/task-status")
    for ts in all_statuses:
        try:
            await _kitsu_api(
                session, "POST",
                f"/data/projects/{project['id']}/settings/task-statuses",
                json_body={"task_status_id": ts["id"]},
            )
        except Exception:
            pass

    # Associate ALL asset types with the project
    all_asset_types = await _kitsu_api(session, "GET", "/data/asset-types")
    for at in (all_asset_types or []):
        try:
            await _kitsu_api(
                session, "POST",
                f"/data/projects/{project['id']}/settings/asset-types",
                json_body={"asset_type_id": at["id"]},
            )
        except Exception:
            pass

    # Associate all task statuses
    all_statuses = await _kitsu_api(session, "GET", "/data/task-status")
    for s in all_statuses:
        try:
            await _kitsu_api(
                session, "POST",
                f"/data/projects/{project['id']}/settings/task-statuses",
                json_body={"task_status_id": s["id"]},
            )
        except Exception:
            pass

    # Create metadata descriptors (custom columns in UI)
    descriptors = [
        {"name": "Style", "field_name": "style",
         "data_type": "string", "entity_type": "Asset"},
        {"name": "Mood", "field_name": "mood",
         "data_type": "string", "entity_type": "Asset"},
        {"name": "Colors", "field_name": "colors",
         "data_type": "string", "entity_type": "Asset"},
        {"name": "Motion", "field_name": "motion",
         "data_type": "list", "choices": ["low", "medium", "high"],
         "entity_type": "Asset"},
        {"name": "AI Prompt", "field_name": "ai_prompt",
         "data_type": "string", "entity_type": "Asset"},
        {"name": "Camera", "field_name": "camera",
         "data_type": "string", "entity_type": "Shot"},
        {"name": "Lens", "field_name": "lens",
         "data_type": "string", "entity_type": "Shot"},
    ]
    for desc in descriptors:
        try:
            await _kitsu_api(
                session, "POST",
                f"/data/projects/{project['id']}/metadata-descriptors",
                json=desc,
            )
        except Exception:
            pass

    return project


async def _kitsu_get_task_type_id(
    session: aiohttp.ClientSession, name: str = "Shot Analysis",
) -> str:
    """Get or create a task type by name. Returns its ID."""
    types = await _kitsu_api(session, "GET", "/data/task-types")
    existing = next((t for t in types if t["name"] == name), None)
    if existing:
        return existing["id"]
    created = await _kitsu_api(session, "POST", "/data/task-types", json_body={"name": name})
    return created["id"]


async def _kitsu_get_todo_status_id(session: aiohttp.ClientSession) -> str:
    """Get the 'Todo' task status ID."""
    statuses = await _kitsu_api(session, "GET", "/data/task-status")
    todo = next((s for s in statuses if s.get("short_name") == "todo"), None)
    if todo:
        return todo["id"]
    return ""


async def _kitsu_get_done_status_id(session: aiohttp.ClientSession) -> str:
    """Get the 'Done' task status ID (by short_name='done')."""
    statuses = await _kitsu_api(session, "GET", "/data/task-status")
    done = next((s for s in statuses if s.get("short_name") == "done"), None)
    if done:
        return done["id"]
    raise RuntimeError("No 'done' task status found in Kitsu")


async def _kitsu_get_status_id(
    session: aiohttp.ClientSession, short_name: str,
) -> str:
    """Get a task status ID by short_name (done, wfa, wip, todo, etc)."""
    statuses = await _kitsu_api(session, "GET", "/data/task-status")
    match = next((s for s in statuses if s.get("short_name") == short_name), None)
    if match:
        return match["id"]
    raise RuntimeError(f"No '{short_name}' task status found in Kitsu")


async def _kitsu_get_entity_type_id(
    session: aiohttp.ClientSession, name: str,
) -> str:
    """Get entity type ID by name (Sequence, Shot, etc)."""
    types = await _kitsu_api(session, "GET", "/data/entity-types")
    match = next((t for t in types if t["name"] == name), None)
    if match:
        return match["id"]
    raise RuntimeError(f"Entity type '{name}' not found in Kitsu")


async def _kitsu_create_sequence(
    session: aiohttp.ClientSession,
    project_id: str,
    episode_id: str,
    name: str,
) -> dict[str, Any]:
    """Create a Sequence under a project/episode."""
    body = {"name": name}
    if episode_id:
        body["episode_id"] = episode_id
    result = await _kitsu_api(
        session, "POST",
        f"/data/projects/{project_id}/sequences",
        body,
    )
    return result


async def _kitsu_get_asset_type_id(
    session: aiohttp.ClientSession,
    name: str,
) -> str:
    """Get asset type ID by name. Falls back to first available type.

    Does NOT create types (requires admin). Uses existing types:
    VideoRef, Environment, Character, Prop, FX.
    """
    types = await _kitsu_api(session, "GET", "/data/asset-types")
    for t in (types or []):
        if t.get("name", "").lower() == name.lower():
            return t["id"]
    # Fallback: use "VideoRef" or first available
    for t in (types or []):
        if t.get("name", "").lower() == "videoref":
            return t["id"]
    return types[0]["id"] if types else ""


async def _kitsu_create_asset(
    session: aiohttp.ClientSession,
    project_id: str,
    asset_type_id: str,
    name: str,
    description: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an asset in a Kitsu project.

    Zou API: POST /data/projects/{project_id}/asset-types/{asset_type_id}/assets/new
    """
    body: dict[str, Any] = {
        "name": name,
        "description": description,
    }
    if data:
        body["data"] = data
    return await _kitsu_api(
        session, "POST",
        f"/data/projects/{project_id}/asset-types/{asset_type_id}/assets/new",
        json_body=body,
    )


async def _kitsu_create_shot(
    session: aiohttp.ClientSession,
    project_id: str,
    sequence_id: str,
    episode_id: str,
    shot_name: str,
    scene_data: dict[str, Any],
) -> dict[str, Any]:
    """Create a Shot under a sequence + episode. Requires Zou >= 1.0.21."""
    body = {
        "name": shot_name,
        "sequence_id": sequence_id,
        "data": scene_data,
    }
    if episode_id:
        body["episode_id"] = episode_id
    return await _kitsu_api(
        session, "POST",
        f"/data/projects/{project_id}/shots",
        json_body=body,
    )


async def _kitsu_get_or_create_task(
    session: aiohttp.ClientSession,
    entity_id: str,
    task_type_id: str,
    project_id: str,
) -> dict[str, Any]:
    """Get existing task or create one. Handles auto-created tasks."""
    # Try to fetch existing task first (Kitsu may auto-create tasks)
    try:
        tasks = await _kitsu_api(
            session, "GET",
            f"/data/entities/{entity_id}/task-types/{task_type_id}/tasks",
        )
        if tasks and isinstance(tasks, list) and tasks:
            return tasks[0]
    except Exception:
        pass

    # No existing task — create one
    # IMPORTANT: Zou needs "name" field to avoid UniqueConstraint on (entity+type+name)
    try:
        tt_info = await _kitsu_api(
            session, "GET", f"/data/task-types/{task_type_id}",
        )
        task_name = tt_info.get("name", "main") if tt_info else "main"
    except Exception:
        task_name = "main"

    try:
        task = await _kitsu_api(
            session, "POST", "/data/tasks",
            json_body={
                "name": task_name,
                "entity_id": entity_id,
                "task_type_id": task_type_id,
                "project_id": project_id,
            },
        )
        # Initialize status to "Todo" — required for /actions/tasks/{id}/comment
        # Without a status, Zou returns 404 on comment endpoint
        todo_id = await _kitsu_get_todo_status_id(session)
        if todo_id and task.get("id"):
            try:
                await _kitsu_api(
                    session, "PUT", f"/data/tasks/{task['id']}",
                    json_body={"task_status_id": todo_id},
                )
            except Exception:
                pass
        return task
    except RuntimeError as e:
        if "already exists" in str(e).lower():
            tasks = await _kitsu_api(
                session, "GET",
                f"/data/entities/{entity_id}/task-types/{task_type_id}/tasks",
            )
            if tasks and isinstance(tasks, list) and tasks:
                return tasks[0]
        raise


async def _kitsu_post_comment(
    session: aiohttp.ClientSession,
    task_id: str,
    status_id: str,
    text: str,
) -> dict[str, Any]:
    """Post a comment on a task, setting status.

    IMPORTANT: Zou API uses field name "comment" (not "text") for the body.
    """
    return await _kitsu_api(
        session, "POST",
        f"/actions/tasks/{task_id}/comment",
        json_body={"task_status_id": status_id, "comment": text},
    )


async def _kitsu_upload_preview(
    session: aiohttp.ClientSession,
    task_id: str,
    comment_id: str,
    frame_data: Path | bytes,
) -> str | None:
    """Upload a keyframe as preview on a comment. Returns preview file ID.

    frame_data: Path to image file, OR raw bytes.
    """
    # Step 1: create preview entry
    preview = await _kitsu_api(
        session, "POST",
        f"/actions/tasks/{task_id}/comments/{comment_id}/add-preview",
        json_body={},
    )
    if not preview or "id" not in preview:
        return None
    preview_id = preview["id"]

    # Step 2: upload the file
    if isinstance(frame_data, bytes):
        img_bytes = frame_data
        filename = "storyboard.png"
    else:
        img_bytes = frame_data.read_bytes()
        filename = frame_data.name

    form = aiohttp.FormData()
    form.add_field(
        "file", img_bytes,
        filename=filename, content_type="image/png",
    )
    await _kitsu_api(
        session, "POST",
        f"/pictures/preview-files/{preview_id}",
        data=form,
    )

    # Step 3: set as main preview
    try:
        await _kitsu_api(
            session, "PUT",
            f"/actions/preview-files/{preview_id}/set-main-preview",
            json_body={},
        )
    except Exception:
        pass  # Non-critical if setting main preview fails

    return preview_id


async def _kitsu_upload_concept_preview(
    session: aiohttp.ClientSession,
    concept_id: str,
    image_bytes: bytes,
) -> str | None:
    """Upload a preview image directly to a Concept entity.

    In Kitsu, concept previews work differently from task previews:
    - POST /data/concepts/{id} with multipart file creates the preview
    - The concept thumbnail is generated from this preview
    """
    if not concept_id or not image_bytes:
        return None

    # Step 1: create a preview file record linked to the concept
    # Zou API: POST /actions/entities/{entity_id}/set-main-preview
    # But first we need to create the preview via a different mechanism.
    #
    # For concepts, the Kitsu web UI uploads directly via:
    # POST /pictures/concepts/{concept_id} (multipart form)
    # This creates a preview_file and sets it as concept thumbnail.
    try:
        form = aiohttp.FormData()
        form.add_field(
            "file", image_bytes,
            filename="mood_board.png", content_type="image/png",
        )
        result = await _kitsu_api(
            session, "POST",
            f"/pictures/concepts/{concept_id}",
            data=form,
        )
        return result.get("id", "") if result else None
    except Exception:
        pass

    # Fallback: use the task-based approach with set-main-preview
    # Create a task on the concept, post comment, upload preview
    try:
        concept_tt = await _kitsu_get_task_type_id(session, "Concept")
        # Get project_id from the concept
        concept_data = await _kitsu_api(
            session, "GET", f"/data/concepts/{concept_id}",
        )
        project_id = concept_data.get("project_id", "") if concept_data else ""
        if not project_id:
            return None

        concept_task = await _kitsu_get_or_create_task(
            session, concept_id, concept_tt, project_id,
        )
        done_id = await _kitsu_get_done_status_id(session)
        comment = await _kitsu_post_comment(
            session, concept_task["id"], done_id,
            "Mood board from video reference",
        )
        if comment and comment.get("id"):
            preview_id = await _kitsu_upload_preview(
                session, concept_task["id"],
                comment["id"], image_bytes,
            )
            # Also try to set concept preview_file_id directly
            if preview_id:
                try:
                    await _kitsu_api(
                        session, "PUT",
                        f"/data/concepts/{concept_id}",
                        json_body={"preview_file_id": preview_id},
                    )
                except Exception:
                    pass
            return preview_id
    except Exception:
        pass

    return None


async def _kitsu_download_asset_preview(
    session: aiohttp.ClientSession,
    asset_id: str,
) -> bytes | None:
    """Download the latest preview image of a Kitsu asset.

    Used for visual consistency: the first keyframe becomes the
    'style anchor' for all subsequent video generations.
    Returns raw image bytes or None if no preview exists.
    """
    try:
        asset = await _kitsu_api(session, "GET", f"/data/assets/{asset_id}")
        if not asset or not asset.get("preview_file_id"):
            return None
        preview_id = asset["preview_file_id"]
        # Download the preview image directly
        headers = {"Authorization": f"Bearer {KITSU_TOKEN}"}
        async with session.get(
            f"{KITSU_URL}/api/pictures/preview-files/{preview_id}.png",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as exc:
        print(f"[kitsu] Preview download error for asset {asset_id}: {exc}", flush=True)
    return None


async def _kitsu_upload_asset_preview(
    session: aiohttp.ClientSession,
    asset_id: str,
    image_bytes: bytes,
    note: str = "Style reference keyframe",
) -> str | None:
    """Upload a keyframe as preview on a Kitsu asset.

    Creates a task 'Reference' on the asset, posts a comment,
    and uploads the image as preview. Sets it as main preview
    so it's visible in the asset library.
    """
    try:
        # Get asset project
        asset = await _kitsu_api(session, "GET", f"/data/assets/{asset_id}")
        if not asset:
            return None
        project_id = asset.get("project_id", "")
        if not project_id:
            return None

        # Get or create "Reference" task type
        ref_tt = await _kitsu_get_task_type_id(session, "Reference")
        if not ref_tt:
            # Fallback to any existing task type
            ref_tt = await _kitsu_get_task_type_id(session, "Concept")
        if not ref_tt:
            return None

        # Get or create task on the asset
        task = await _kitsu_get_or_create_task(session, asset_id, ref_tt, project_id)
        if not task:
            return None

        # Post comment + upload preview
        done_id = await _kitsu_get_done_status_id(session)
        comment = await _kitsu_post_comment(session, task["id"], done_id, note)
        if comment and comment.get("id"):
            preview_id = await _kitsu_upload_preview(
                session, task["id"], comment["id"], image_bytes,
            )
            # Set as asset main preview
            if preview_id:
                try:
                    await _kitsu_api(
                        session, "PUT",
                        f"/data/assets/{asset_id}",
                        json_body={"preview_file_id": preview_id},
                    )
                except Exception:
                    pass
            return preview_id
    except Exception as exc:
        print(f"[kitsu] Asset preview upload error {asset_id}: {exc}", flush=True)
    return None


async def _kitsu_create_playlist(
    session: aiohttp.ClientSession,
    project_id: str,
    name: str,
    shot_ids: list[str],
) -> dict[str, Any] | None:
    """Create a playlist in Kitsu for review with actual preview files."""
    try:
        # Fetch preview_file_id for each shot (so the playlist shows real frames)
        shots_payload = []
        for sid in shot_ids:
            preview_id = ""
            try:
                entity = await _kitsu_api(session, "GET", f"/data/entities/{sid}")
                preview_id = entity.get("preview_file_id", "") or ""
            except Exception:
                pass
            shots_payload.append({"entity_id": sid, "preview_file_id": preview_id})

        return await _kitsu_api(
            session, "POST",
            f"/data/projects/{project_id}/playlists",
            json_body={"name": name, "shots": shots_payload},
        )
    except Exception:
        return None


async def _kitsu_cast_asset_to_shot(
    session: aiohttp.ClientSession,
    project_id: str,
    shot_id: str,
    asset_id: str,
) -> bool:
    """Cast an asset into a shot (breakdown link).

    This makes the asset appear in the shot's breakdown view in Kitsu.
    Used for character consistency: the character asset is linked to all
    shots where it appears.
    """
    try:
        # Get current casting
        current = await _kitsu_api(
            session, "GET",
            f"/data/projects/{project_id}/entities/{shot_id}/casting",
        )
        # Add new asset if not already cast
        casting = current if isinstance(current, list) else []
        if not any(c.get("asset_id") == asset_id for c in casting):
            casting.append({"asset_id": asset_id, "nb_occurences": 1})
            await _kitsu_api(
                session, "PUT",
                f"/data/projects/{project_id}/entities/{shot_id}/casting",
                casting,
            )
        return True
    except Exception:
        return False


async def _kitsu_set_task_estimation(
    session: aiohttp.ClientSession,
    task_id: str,
    cost_usd: float = 0.0,
    duration_seconds: int = 0,
) -> bool:
    """Set estimation on a task (cost as duration proxy, visible in schedule).

    Kitsu tracks estimation in seconds. We encode the AI model cost
    as "estimation" so it appears in the schedule/budget views.
    Convention: 1 USD = 3600 seconds (1 hour) for visual representation.
    """
    try:
        estimation_sec = int(cost_usd * 3600) if cost_usd > 0 else duration_seconds
        await _kitsu_api(
            session, "PUT", f"/data/tasks/{task_id}",
            json_body={"estimation": estimation_sec},
        )
        return True
    except Exception:
        return False


async def push_to_kitsu(
    filename: str,
    scenes: list[dict[str, float]],
    scene_analyses: list[dict[str, Any]],
    synthesis: dict[str, Any],
    frames: list[Path],
    colors: list[str],
    motion: dict[str, Any],
) -> dict[str, Any]:
    """Push multi-scene analysis to Kitsu: 1 Sequence + N Shots."""
    if not KITSU_URL or not KITSU_TOKEN:
        return {"skipped": "KITSU not configured"}

    try:
        async with aiohttp.ClientSession() as session:
            project = await _kitsu_get_asset_library(session)
            project_id = project["id"]
            episode_id = project.get("first_episode_id", "")

            shot_task_type_id = await _kitsu_get_task_type_id(
                session, "Shot Analysis",
            )
            done_status_id = await _kitsu_get_done_status_id(session)

            # Create Sequence for this video
            seq_name = Path(filename).stem[:80]
            sequence = await _kitsu_create_sequence(
                session, project_id, episode_id, seq_name,
            )
            sequence_id = sequence["id"]

            # Store synthesis as sequence description (no task on sequence)
            synthesis_text = _format_synthesis(synthesis, colors, motion)
            try:
                await _kitsu_api(
                    session, "PUT",
                    f"/data/entities/{sequence_id}",
                    json_body={"description": synthesis_text},
                )
            except Exception:
                pass  # Non-critical

            # Phase 1: Create all Shots (1 per scene)
            shot_ids: list[str] = []
            for idx, (scene, analysis) in enumerate(
                zip(scenes, scene_analyses, strict=False)
            ):
                shot_name = f"SH{(idx + 1) * 10:04d}"
                scene_meta = {
                    "start": scene.get("start", 0),
                    "end": scene.get("end", 0),
                    "duration": round(
                        scene.get("end", 0) - scene.get("start", 0), 3
                    ),
                    "style": analysis.get("style", ""),
                    "mood": analysis.get("mood", ""),
                }
                shot = await _kitsu_create_shot(
                    session, project_id, sequence_id, episode_id,
                    shot_name, scene_meta,
                )
                shot_ids.append(shot["id"])

            # Phase 2: Bulk create tasks for all shots
            await _kitsu_api(
                session, "POST",
                f"/actions/projects/{project_id}/task-types"
                f"/{shot_task_type_id}/shots/create-tasks",
                json_body={},
            )

            # Phase 3: Post comments + previews on each shot
            task_count = 0
            comment_count = 0
            preview_count = 0
            for idx, (shot_id, scene, analysis) in enumerate(
                zip(shot_ids, scenes, scene_analyses, strict=False)
            ):
                # Fetch the auto-created task
                shot_tasks = await _kitsu_api(
                    session, "GET",
                    f"/data/shots/{shot_id}/tasks",
                )
                task = next(
                    (t for t in (shot_tasks or [])
                     if t.get("task_type_id") == shot_task_type_id),
                    None,
                )
                if not task:
                    continue
                task_count += 1
                comment_text = _format_scene_analysis(idx, scene, analysis)
                comment = await _kitsu_post_comment(
                    session, task["id"], done_status_id, comment_text,
                )
                if comment and "id" in comment:
                    comment_count += 1

                    # Upload keyframe as preview
                    if idx < len(frames) and frames[idx].exists():
                        pid = await _kitsu_upload_preview(
                            session, task["id"], comment["id"], frames[idx],
                        )
                        if pid:
                            preview_count += 1

            # Phase 4: Create Assets (1 per scene — visible in Assets tab)
            videoref_type_id = await _kitsu_get_entity_type_id(
                session, "VideoRef",
            )
            asset_count = 0
            for idx, analysis in enumerate(scene_analyses):
                # Short descriptive name: Subject-Style-Mood (max 40 chars)
                asset_name = _generate_asset_name(analysis, filename)
                asset_name = f"{asset_name}-S{idx+1:02d}"
                asset_data = {
                    "style": analysis.get("style", ""),
                    "mood": analysis.get("mood", ""),
                    "colors": ", ".join(colors[:5]) if idx == 0 else "",
                    "motion": motion.get("motion_level", "low"),
                    "ai_prompt": analysis.get("suggested_prompt", "")[:500],
                }
                desc = (
                    f"Style: {analysis.get('style', '')}\n"
                    f"Mood: {analysis.get('mood', '')}\n"
                    f"Prompt: {analysis.get('suggested_prompt', '')[:200]}"
                )
                try:
                    await _kitsu_api(
                        session, "POST",
                        f"/data/projects/{project_id}/asset-types"
                        f"/{videoref_type_id}/assets/new",
                        json_body={
                            "name": asset_name,
                            "description": desc,
                            "data": asset_data,
                        },
                    )
                    asset_count += 1
                except Exception:
                    pass  # Non-critical — shots are primary

            return {
                "sequence_id": sequence_id,
                "sequence_name": seq_name,
                "shot_count": len(shot_ids),
                "asset_count": asset_count,
                "task_count": task_count,
                "comment_count": comment_count,
                "preview_count": preview_count,
                "project_id": project_id,
            }
    except Exception as exc:
        return {"error": str(exc)}


def _format_synthesis(
    synthesis: dict[str, Any], colors: list[str], motion: dict[str, Any],
) -> str:
    """Format synthesis analysis as readable text for Kitsu comment."""
    lines = [
        f"Overall Style: {synthesis.get('overall_style', 'N/A')}",
        f"Narrative Arc: {synthesis.get('narrative_arc', 'N/A')}",
        f"Dominant Mood: {synthesis.get('dominant_mood', 'N/A')}",
        f"Visual Coherence: {synthesis.get('visual_coherence', 'N/A')}",
        f"Colors: {', '.join(colors[:5])}",
        f"Motion: {motion.get('motion_level', 'N/A')} (score: {motion.get('motion_score', '?')})",
        f"Prompt: {synthesis.get('suggested_prompt', 'N/A')[:300]}",
    ]
    return "\n".join(lines)


def _format_scene_analysis(
    idx: int, scene: dict[str, float], analysis: dict[str, Any],
) -> str:
    """Format per-scene analysis as readable text for Kitsu comment."""
    lines = [
        f"Scene {idx + 1} ({scene['start']:.1f}s - {scene['end']:.1f}s)",
        f"Style: {analysis.get('style', 'N/A')}",
        f"Mood: {analysis.get('mood', 'N/A')}",
        f"Lighting: {analysis.get('lighting', 'N/A')}",
        f"Composition: {analysis.get('composition', 'N/A')}",
        f"Color Grade: {analysis.get('color_grade', 'N/A')}",
        f"Prompt: {analysis.get('suggested_prompt', 'N/A')[:300]}",
    ]
    return "\n".join(lines)


# ============================================================
# 10. Qdrant semantic indexing
# ============================================================
async def index_in_qdrant(
    filename: str, synthesis: dict[str, Any],
    scene_analyses: list[dict[str, Any]],
    colors: list[str], motion: dict[str, Any],
) -> dict[str, Any]:
    """Generate embedding via LiteLLM and index in Qdrant."""
    if not QDRANT_URL or not QDRANT_API_KEY:
        return {"skipped": "QDRANT not configured"}
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"skipped": "LITELLM not configured (needed for embeddings)"}

    style = synthesis.get("overall_style", synthesis.get("style", ""))
    mood = synthesis.get("dominant_mood", synthesis.get("mood", ""))
    prompt = synthesis.get("suggested_prompt", "")
    text = (
        f"Video reference: {filename}. "
        f"Style: {style}. Mood: {mood}. "
        f"Colors: {', '.join(colors[:5])}. "
        f"Motion: {motion.get('motion_level', 'unknown')}. "
        f"Scenes: {len(scene_analyses)}. "
        f"Prompt: {prompt}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/embeddings",
                json={"model": "embedding", "input": text},
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return {"error": f"Embedding failed: {resp.status} {body[:200]}"}
                emb_data = await resp.json()
                vector = emb_data["data"][0]["embedding"]

            point_id = int(hashlib.sha256(filename.encode()).hexdigest()[:15], 16)
            payload = {
                "filename": filename,
                "style": style,
                "mood": mood,
                "colors": colors[:5],
                "motion_level": motion.get("motion_level", "unknown"),
                "scene_count": len(scene_analyses),
                "suggested_prompt": prompt[:500],
                "synthesis": json.dumps(synthesis)[:2000],
            }
            async with session.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points",
                json={"points": [{"id": point_id, "vector": vector, "payload": payload}]},
                headers={"api-key": QDRANT_API_KEY, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return {"error": f"Qdrant upsert: {resp.status} {body[:200]}"}
                return {"indexed": True, "point_id": point_id}
    except Exception as exc:
        return {"error": str(exc)}


async def _search_qdrant(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Qdrant for similar references. Returns list of results."""
    if not QDRANT_URL or not LITELLM_URL:
        return []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/embeddings",
                json={"model": "embedding", "input": query},
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                emb = await resp.json()
                vector = emb["data"][0]["embedding"]

            async with session.post(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
                json={"vector": vector, "limit": limit, "with_payload": True},
                headers={"api-key": QDRANT_API_KEY, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    {**hit.get("payload", {}), "score": hit.get("score", 0)}
                    for hit in data.get("result", [])
                ]
    except Exception:
        return []


# ============================================================
# 11. Gitea versioning
# ============================================================
async def version_in_gitea(filename: str, result: dict[str, Any]) -> dict[str, Any]:
    """Push analysis result as JSON to Gitea comfyui-templates repo."""
    if not GITEA_URL or not GITEA_TOKEN:
        return {"skipped": "GITEA not configured"}

    stem = Path(filename).stem
    file_path = f"analyses/{stem}.json"
    content_b64 = base64.b64encode(json.dumps(result, indent=2).encode()).decode()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GITEA_URL}/api/v1/repos/mobuone/comfyui-templates/contents/{file_path}?ref=main",
                headers={"Authorization": f"token {GITEA_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                sha = ""
                if resp.status == 200:
                    existing = await resp.json()
                    sha = existing.get("sha", "")

            method = "PUT" if sha else "POST"
            body: dict[str, Any] = {"message": f"analysis: {stem}", "content": content_b64}
            if sha:
                body["sha"] = sha

            url = f"{GITEA_URL}/api/v1/repos/mobuone/comfyui-templates/contents/{file_path}"
            async with session.request(
                method, url, json=body,
                headers={"Authorization": f"token {GITEA_TOKEN}", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201):
                    return {"versioned": True, "path": file_path}
                body_text = await resp.text()
                return {"error": f"Gitea {resp.status}: {body_text[:200]}"}
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# 12. Full analysis pipeline
# ============================================================
async def run_analysis(filename: str, template_name: str = "default") -> dict[str, Any]:
    """Run the full multi-scene analysis pipeline. Returns immutable result dict."""
    src = WATCH_DIR / filename
    if not src.exists():
        return {"filename": filename, "status": "error", "error": f"File not found: {filename}"}

    try:
        # Phase 1: Video info + scene detection
        info = await _get_video_info(src)
        scenes = await detect_scenes(src)
        motion = estimate_motion(info)

        # Phase 2: Extract 1 keyframe per scene
        frames = await extract_scene_keyframes(src, scenes)

        # Phase 3: Per-scene color extraction (from each keyframe)
        all_colors: list[list[str]] = []
        for frame in frames:
            colors = await extract_colors(frame)
            all_colors.append(colors)
        # Aggregate: use first scene's palette as primary
        primary_colors = all_colors[0] if all_colors else []

        # Phase 4: Per-scene Claude Vision analysis
        scene_analyses: list[dict[str, Any]] = []
        if LITELLM_URL:
            for idx, frame in enumerate(frames):
                scene_colors = all_colors[idx] if idx < len(all_colors) else primary_colors
                analysis = await analyze_scene(frame, idx, scene_colors, motion)
                scene_analyses.append(analysis)
        else:
            scene_analyses = [{}] * len(scenes)

        # Phase 5: Whole-video synthesis
        synthesis: dict[str, Any] = {}
        if LITELLM_URL and scene_analyses:
            synthesis = await synthesize_video(scene_analyses, filename, info)

        # Phase 6: ComfyUI workflow generation
        template = await fetch_template(template_name)
        workflow = generate_workflow(template, synthesis, primary_colors)
        wf_path = COMFYUI_DIR / f"{Path(filename).stem}_workflow.json"
        wf_path.write_text(json.dumps(workflow, indent=2))

        # Build scenes result array
        scenes_result = []
        for idx, scene in enumerate(scenes):
            entry: dict[str, Any] = {
                "index": idx,
                "start": scene["start"],
                "end": scene["end"],
                "duration": round(scene["end"] - scene["start"], 3),
                "keyframe": frames[idx].name if idx < len(frames) else None,
                "colors": all_colors[idx] if idx < len(all_colors) else [],
                "analysis": scene_analyses[idx] if idx < len(scene_analyses) else {},
            }
            scenes_result.append(entry)

        result: dict[str, Any] = {
            "filename": filename,
            "version": VERSION,
            "status": "completed",
            "size_bytes": src.stat().st_size,
            "video_info": info,
            "motion": motion,
            "scene_count": len(scenes),
            "scenes": scenes_result,
            "synthesis": synthesis,
            "primary_colors": primary_colors,
            "workflow_path": str(wf_path),
        }

        # Phase 7: Push to Kitsu (Sequence + Shots)
        result["kitsu"] = await push_to_kitsu(
            filename, scenes, scene_analyses, synthesis,
            frames, primary_colors, motion,
        )

        # Phase 8: Index in Qdrant
        result["qdrant"] = await index_in_qdrant(
            filename, synthesis, scene_analyses, primary_colors, motion,
        )

        # Phase 9: Version in Gitea
        result["gitea"] = await version_in_gitea(filename, result)

        return result

    except Exception as exc:
        return {"filename": filename, "status": "error", "error": str(exc)}


# ============================================================
# 13. Camera presets loader
# ============================================================
async def _load_camera_presets() -> dict[str, Any]:
    """Fetch camera-presets.json from Gitea (cached after first load)."""
    global _camera_presets_cache
    if _camera_presets_cache is not None:
        return _camera_presets_cache

    if not GITEA_URL or not GITEA_TOKEN:
        return {"cameras": {}, "lenses": {}, "apertures": {}, "motions": {}}

    url = (
        f"{GITEA_URL}/api/v1/repos/mobuone/comfyui-templates"
        f"/raw/camera-presets.json?ref=main"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"Authorization": f"token {GITEA_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    _camera_presets_cache = await resp.json()
                    return _camera_presets_cache
    except Exception as exc:
        print(f"[camera-presets] Failed to load from Gitea: {exc}")

    # Fallback: try with urllib (sync, simpler SSL)
    try:
        import urllib.request as _ur
        req = _ur.Request(url, headers={"Authorization": f"token {GITEA_TOKEN}"})
        with _ur.urlopen(req, timeout=10) as resp:
            _camera_presets_cache = json.loads(resp.read())
            print(f"[camera-presets] Loaded via urllib fallback")
            return _camera_presets_cache
    except Exception as exc2:
        print(f"[camera-presets] urllib fallback also failed: {exc2}")

    fallback = {"cameras": {}, "lenses": {}, "apertures": {}, "motions": {}}
    _camera_presets_cache = fallback
    return fallback


def _inject_camera_tokens(
    prompt: str,
    camera: str = "",
    lens: str = "",
    aperture: str = "",
    motion: str = "",
) -> str:
    """Append camera tokens to a prompt string. Returns new string."""
    tokens = []
    if camera:
        tokens.append(f"shot on {camera}")
    if lens:
        tokens.append(f"{lens} lens")
    if aperture:
        tokens.append(f"f/{aperture}")
    if motion:
        tokens.append(f"{motion} camera movement")
    if not tokens:
        return prompt
    return f"{prompt}, {', '.join(tokens)}"


# ============================================================
# 14. Job state management
# ============================================================
def _job_path(job_id: str) -> Path:
    """Return path to a job state JSON file."""
    return JOBS_DIR / f"{job_id}.json"


def _load_job(job_id_or_slug: str) -> dict[str, Any] | None:
    """Load a job by UUID or slug. Returns None if not found."""
    # Try direct UUID match first
    path = _job_path(job_id_or_slug)
    if path.exists():
        return json.loads(path.read_text())

    # Search by slug
    if JOBS_DIR.exists():
        for f in JOBS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("slug") == job_id_or_slug:
                    return data
            except Exception:
                continue
    return None


def _save_job(job: dict[str, Any]) -> None:
    """Save a job to disk. Creates new dict to avoid mutation."""
    path = _job_path(job["job_id"])
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    saved = {**job, "updated_at": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(saved, indent=2))


def _slugify(title: str, uid: str) -> str:
    """Generate a human-readable slug from title + short UUID."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"{slug}-{uid[:4]}"


RESOLUTION_PRESETS = {
    "landscape": {"resolution": "1920x1080", "ratio": "16:9"},
    "portrait": {"resolution": "1080x1920", "ratio": "9:16"},
    "square": {"resolution": "1080x1080", "ratio": "1:1"},
    "4k": {"resolution": "3840x2160", "ratio": "16:9"},
    "4k-portrait": {"resolution": "2160x3840", "ratio": "9:16"},
    "cinescope": {"resolution": "2560x1080", "ratio": "21:9"},
}


def _new_job(
    title: str,
    url: str = "",
    camera: str = "",
    lens: str = "",
    aperture: str = "",
    motion: str = "",
    fps: str = "24",
    format: str = "landscape",
    style: str = "2d3d",
) -> dict[str, Any]:
    """Create a new immutable job state dict."""
    now = datetime.now(timezone.utc).isoformat()
    job_id = str(uuid.uuid4())
    slug = _slugify(title, job_id)
    preset = RESOLUTION_PRESETS.get(format, RESOLUTION_PRESETS["landscape"])
    return {
        "job_id": job_id,
        "slug": slug,
        "title": title,
        "url": url,
        "camera": camera,
        "lens": lens,
        "aperture": aperture,
        "motion": motion,
        "fps": fps,
        "resolution": preset["resolution"],
        "ratio": preset["ratio"],
        "format": format,
        "style": style,
        "current_step": None,
        "steps_completed": [],
        "kitsu_project_id": "",
        "kitsu_sequence_id": "",
        "kitsu_shot_ids": [],
        "scenes": [],
        "scene_analyses": [],
        "created_at": now,
        "updated_at": now,
    }


def _advance_job(job: dict[str, Any], step_id: str, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return new job dict with step marked completed. Immutable."""
    completed = list(job["steps_completed"])
    if step_id not in completed:
        completed.append(step_id)
    # Find next step
    current_idx = STEP_IDS.index(step_id) if step_id in STEP_IDS else -1
    next_step = STEP_IDS[current_idx + 1] if current_idx + 1 < len(STEP_IDS) else None
    updated = {
        **job,
        "current_step": next_step,
        "steps_completed": completed,
    }
    if extras:
        updated = {**updated, **extras}
    return updated


# ============================================================
# 15. Telegram notification helper
# ============================================================
async def _send_telegram(message: str) -> bool:
    """Send a Telegram notification to the Studio topic. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    if TELEGRAM_TOPIC_ID:
        payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[telegram] sendMessage failed: {resp.status} {body[:200]}", flush=True)
                return resp.status == 200
    except Exception as exc:
        print(f"[telegram] sendMessage error: {exc}", flush=True)
        return False


async def _send_telegram_photo(
    image_bytes: bytes, caption: str = "",
) -> bool:
    """Send a photo to the Studio topic via Telegram bot. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", TELEGRAM_CHAT_ID)
        if TELEGRAM_TOPIC_ID:
            form.add_field("message_thread_id", TELEGRAM_TOPIC_ID)
        form.add_field(
            "photo", image_bytes,
            filename="preview.png", content_type="image/png",
        )
        if caption:
            form.add_field("caption", caption[:1024])
            form.add_field("parse_mode", "Markdown")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data=form,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[telegram] sendPhoto failed: {resp.status} {body[:200]}", flush=True)
                return resp.status == 200
    except Exception as exc:
        print(f"[telegram] sendPhoto error: {exc}", flush=True)
        return False


async def _send_telegram_video(
    video_bytes: bytes, caption: str = "",
) -> bool:
    """Send a video to the Studio topic via Telegram bot. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", TELEGRAM_CHAT_ID)
        if TELEGRAM_TOPIC_ID:
            form.add_field("message_thread_id", TELEGRAM_TOPIC_ID)
        form.add_field(
            "video", video_bytes,
            filename="clip.mp4", content_type="video/mp4",
        )
        if caption:
            form.add_field("caption", caption[:1024])
            form.add_field("parse_mode", "Markdown")
        # Telegram accepts up to 50MB for bots
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data=form,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    print(f"[telegram] sendVideo failed: {resp.status} {body[:200]}", flush=True)
                else:
                    print(f"[telegram] sendVideo OK ({len(video_bytes)} bytes)", flush=True)
                return ok
    except Exception as exc:
        print(f"[telegram] sendVideo error: {exc}", flush=True)
        return False


async def _send_telegram_video_url(
    video_url: str, job: dict[str, Any], step_id: str,
) -> bool:
    """Send a video URL to Telegram (Telegram downloads & streams it)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    title = job.get("title", "Unknown")
    slug = job.get("slug", job.get("job_id", "?")[:12])
    completed = len(job.get("steps_completed", [])) + 1
    total = len(PIPELINE_STEPS)
    step_info = STEP_MAP.get(step_id, {})
    step_label = step_info.get("task_type", step_id)

    kitsu_base = KITSU_URL or "https://boss.ewutelo.cloud"
    caption = (
        f"*{step_label}* termine\n"
        f"Production: *{title}*\n"
        f"Progression: {completed}/{total}\n"
        f"[Ouvrir Kitsu]({kitsu_base})\n"
        f"Job: `{slug}`"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "video": video_url,
            "caption": caption[:1024],
            "parse_mode": "Markdown",
        }
        if TELEGRAM_TOPIC_ID:
            payload["message_thread_id"] = int(TELEGRAM_TOPIC_ID)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    print(f"[telegram] sendVideo URL failed: {resp.status} {body[:200]}", flush=True)
                else:
                    print(f"[telegram] sendVideo URL OK", flush=True)
                return ok
    except Exception as exc:
        print(f"[telegram] sendVideo URL error: {exc}", flush=True)
        return False


async def _notify_step_completed(
    job: dict[str, Any], step_id: str,
    preview_bytes: bytes | None = None,
    video_bytes: bytes | None = None,
) -> bool:
    """Send Telegram notification after each pipeline step.

    Sends video if video_bytes, photo if preview_bytes, otherwise text-only.
    """
    title = job.get("title", "Unknown")
    slug = job.get("slug", job["job_id"][:12])
    completed = len(job.get("steps_completed", [])) + 1
    total = len(PIPELINE_STEPS)
    step_info = STEP_MAP.get(step_id, {})
    step_label = step_info.get("task_type", step_id)
    needs_human = step_info.get("needs_human", False)

    kitsu_base = KITSU_URL or "https://boss.ewutelo.cloud"
    gate = "\n\n*Validation requise* — repondre dans Kitsu" if needs_human else ""
    msg = (
        f"*{step_label}* termine\n"
        f"Production: *{title}*\n"
        f"Progression: {completed}/{total}\n"
        f"[Ouvrir Kitsu]({kitsu_base}){gate}\n"
        f"Job: `{slug}`"
    )

    if video_bytes:
        return await _send_telegram_video(video_bytes, msg)
    if preview_bytes:
        return await _send_telegram_photo(preview_bytes, msg)
    return await _send_telegram(msg)


# ============================================================
# 16. N8N creative pipeline caller
# ============================================================
async def _call_n8n_creative(
    prompt: str,
    output_type: str = "image",
    resolution: str = "low-res",
    scene_index: int = 0,
    job_id: str = "",
) -> dict[str, Any]:
    """Call n8n creative-pipeline webhook. Returns result dict."""
    if not N8N_CREATIVE_PIPELINE_URL:
        return {"skipped": "N8N_CREATIVE_PIPELINE_URL not configured"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                N8N_CREATIVE_PIPELINE_URL,
                json={
                    "prompt": prompt,
                    "output_type": output_type,
                    "resolution": resolution,
                    "scene_index": scene_index,
                    "job_id": job_id,
                },
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                body = await resp.text()
                return {"error": f"n8n {resp.status}: {body[:200]}"}
    except Exception as exc:
        return {"error": str(exc)}


async def _call_n8n_video(
    prompt: str,
    scene_index: int = 0,
    job_id: str = "",
) -> dict[str, Any]:
    """Call n8n video-generate webhook. Returns result dict."""
    if not N8N_CREATIVE_PIPELINE_URL:
        return {"skipped": "N8N_CREATIVE_PIPELINE_URL not configured"}
    video_url = N8N_CREATIVE_PIPELINE_URL.replace("creative-pipeline", "video-generate")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                video_url,
                json={
                    "prompt": prompt,
                    "scene_index": scene_index,
                    "job_id": job_id,
                },
                timeout=aiohttp.ClientTimeout(total=600),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                body = await resp.text()
                return {"error": f"n8n video {resp.status}: {body[:200]}"}
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# 16b. Workflow Composer — intelligent model routing
# ============================================================
async def _composer_select_model(
    task: str, budget: str = "balanced",
) -> dict[str, Any] | None:
    """Search model-registry in Qdrant for the best model matching task + budget.

    Returns the model payload (node, name, quality, cost, notes) or None.
    """
    if not QDRANT_URL or not QDRANT_API_KEY or not LITELLM_URL:
        return None

    try:
        # Get embedding for the task description
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/embeddings",
                json={"model": "embedding", "input": f"{task} {budget} quality"},
                headers={"Authorization": f"Bearer {LITELLM_API_KEY}",
                         "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                emb = await resp.json()
                vector = emb["data"][0]["embedding"]

            # Search with budget filter
            search_payload = {
                "vector": vector,
                "limit": 5,
                "with_payload": True,
                "filter": {
                    "must": [
                        {"key": "budget", "match": {"any": _budget_tiers(budget)}},
                    ],
                },
            }

            async with session.post(
                f"{QDRANT_URL}/collections/{MODEL_REGISTRY_COLLECTION}/points/search",
                json=search_payload,
                headers={"api-key": QDRANT_API_KEY, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                results = data.get("result", [])

                # Pick best result that matches task type
                candidates: list[dict[str, Any]] = []
                # If task mentions "image" or "storyboard", skip video models
                is_image_task = any(
                    w in task.lower()
                    for w in ["image", "storyboard", "keyframe", "character", "inpaint", "upscale"]
                )
                is_video_task = any(
                    w in task.lower()
                    for w in ["video", "animate", "clip", "motion"]
                )

                for hit in results:
                    p = hit["payload"]
                    node = p.get("node", "").lower()
                    name = p.get("name", "").lower()
                    print(f"[model-select] candidate: {p.get('node')} score={hit.get('score',0):.3f} tasks={p.get('tasks',[])} budget={p.get('budget')}", flush=True)

                    # Task-based filtering: check model's tasks match the query intent
                    model_tasks = set(p.get("tasks", []))

                    # Skip video models for image tasks
                    if is_image_task and not is_video_task:
                        if any(v in node or v in name for v in [
                            "video", "kling", "veo", "seedance", "runway",
                            "sora", "luma", "minimax", "wan2", "animate",
                        ]):
                            print(f"[model-select] SKIP (video model): {p.get('node')}", flush=True)
                            continue
                        # Skip upscale-only models for generation tasks
                        if model_tasks and model_tasks <= {"upscale", "enhance"}:
                            print(f"[model-select] SKIP (upscale-only): {p.get('node')}", flush=True)
                            continue

                    # Skip image models for video tasks
                    if is_video_task and not is_image_task:
                        if not any(v in node or v in name for v in [
                            "video", "kling", "veo", "seedance", "runway",
                            "sora", "luma", "minimax", "wan2", "animate",
                        ]):
                            print(f"[model-select] SKIP (non-video model): {p.get('node')}", flush=True)
                            continue

                    candidates.append(p)

                if not candidates:
                    # Fallback: return first result regardless
                    return results[0]["payload"] if results else None

                # Prefer direct providers over fal.ai intermediaries
                direct = [c for c in candidates if "-direct" in c.get("provider", "")]
                selected = direct[0] if direct else candidates[0]
                print(f"[model-select] SELECTED: {selected.get('node')} (provider={selected.get('provider', '?')})", flush=True)
                return selected
    except Exception as exc:
        print(f"[composer] Model selection error: {exc}")
        return None


def _budget_tiers(budget: str) -> list[str]:
    """Return allowed budget tiers for a given budget level."""
    if budget == "eco":
        return ["eco"]
    if budget == "balanced":
        return ["eco", "balanced"]
    return ["eco", "balanced", "premium"]


def _resolve_aspect_ratio(width: int, height: int) -> str:
    """Compute best standard aspect ratio from pixel dimensions."""
    ratio = width / height if height > 0 else 1.0
    if ratio > 1.8:
        return "21:9"
    if ratio > 1.4:
        return "16:9"
    if ratio > 1.2:
        return "4:3"
    if ratio > 0.85:
        return "1:1"
    if ratio > 0.65:
        return "3:4"
    if ratio > 0.5:
        return "9:16"
    return "9:21"


# Node specs from ComfyUI-fal-API source code (2026-03-20).
# IMAGE nodes return IMAGE tensor → need SaveImage.
# VIDEO nodes return STRING (URL) → NO SaveImage.
_FAL_NODE_SPECS: dict[str, dict[str, Any]] = {
    # === IMAGE NODES (return IMAGE tensor) ===
    "NanoBananaTextToImage_fal": {
        "output": "IMAGE",
        "size_param": "aspect_ratio",
        "extra_defaults": {},
    },
    "NanoBanana2_fal": {
        "output": "IMAGE",
        "size_param": "aspect_ratio+resolution",
        "extra_defaults": {"resolution": "1K"},
    },
    "NanoBananaPro_fal": {
        "output": "IMAGE",
        "size_param": "aspect_ratio+resolution",
        "extra_defaults": {"resolution": "2K"},
    },
    "Imagen4Preview_fal": {
        "output": "IMAGE",
        "size_param": None,  # prompt only, zero options
        "extra_defaults": {},
    },
    "FluxSchnell_fal": {
        "output": "IMAGE",
        "size_param": "image_size",
        "extra_defaults": {"num_inference_steps": 4},
    },
    "FluxUltra_fal": {
        "output": "IMAGE",
        "size_param": "aspect_ratio",
        "extra_defaults": {"raw": False},
    },
    "FluxProKontextTextToImage_fal": {
        "output": "IMAGE",
        "size_param": "aspect_ratio",
        "extra_defaults": {},
    },
    "FluxLora_fal": {
        "output": "IMAGE",
        "size_param": "image_size",
        "extra_defaults": {"num_inference_steps": 28, "guidance_scale": 3.0},
    },
    "GPTImage15_fal": {
        "output": "IMAGE",
        "size_param": "image_size_wxh",  # "1024x1024", "1536x1024", "1024x1536"
        "extra_defaults": {"quality": "high"},
    },
    "Recraft_fal": {
        "output": "IMAGE",
        "size_param": "image_size",
        "extra_defaults": {"style": "realistic_image"},
    },
    "Ideogramv3_fal": {
        "output": "IMAGE",
        "size_param": "image_size",
        "extra_defaults": {},
    },
    "Hidreamfull_fal": {
        "output": "IMAGE",
        "size_param": "image_size",
        "extra_defaults": {},
    },
    "Dreamina31TextToImage_fal": {
        "output": "IMAGE",
        "size_param": "image_size_preset",  # presets only, no w/h
        "extra_defaults": {},
    },
    # === VIDEO NODES (return STRING = URL, NO SaveImage) ===
    "SeedanceTextToVideo_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",  # "5", "10"
        "size_param": "aspect_ratio+resolution_p",
        "extra_defaults": {"resolution": "720p", "camera_fixed": False},
    },
    "SeedanceImageToVideo_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": "resolution_p",  # "480p", "720p"
        "needs_image": True,
        "extra_defaults": {"resolution": "720p", "camera_fixed": False},
    },
    "Kling25TurboPro_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": None,  # no aspect_ratio
        "needs_image": True,
        "extra_defaults": {"negative_prompt": "blur, distort, and low quality", "cfg_scale": 0.5},
    },
    "Kling26Pro_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": "aspect_ratio",  # t2v only
        "extra_defaults": {"negative_prompt": "blur, distort, and low quality", "generate_audio": True},
    },
    "KlingMaster_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": "aspect_ratio",
        "extra_defaults": {},
    },
    "Kling21Pro_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": None,
        "needs_image": True,
        "extra_defaults": {"negative_prompt": "blur, distort, and low quality", "cfg_scale": 0.5},
    },
    "Veo3_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str_s",  # "8s"
        "duration_values": ["8s"],  # fixed
        "size_param": "aspect_ratio",
        "extra_defaults": {"enhance_prompt": True, "generate_audio": True},
    },
    "Veo31_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str_s",  # "4s", "6s", "8s"
        "size_param": "aspect_ratio+resolution_p",
        "needs_image": True,
        "image_param": "first_frame",  # NOT "image"
        "extra_defaults": {"resolution": "720p", "generate_audio": True},
    },
    "Veo31Fast_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str_s",
        "size_param": "aspect_ratio+resolution_p",
        "needs_image": True,
        "image_param": "first_frame",
        "extra_defaults": {"resolution": "720p", "generate_audio": True},
    },
    "Veo2ImageToVideo_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str_s",  # "5s"-"8s"
        "size_param": "aspect_ratio",
        "needs_image": True,
        "extra_defaults": {},
    },
    "LumaDreamMachine_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": "aspect_ratio",
        "extra_defaults": {"mode": "text-to-video"},
    },
    "RunwayGen3_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": None,
        "needs_image": True,
        "extra_defaults": {},
    },
    "Sora2Pro_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "int",  # 4, 8, 12 (integers!)
        "size_param": "aspect_ratio+resolution_p",
        "needs_image": True,
        "extra_defaults": {"resolution": "720p"},
    },
    "WanPro_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "needs_image": True,
        "extra_defaults": {},
    },
    "Wan25_preview_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": "resolution_p",
        "needs_image": True,
        "extra_defaults": {"resolution": "1080p"},
    },
    "Wan26_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",  # "5", "10", "15"
        "size_param": "aspect_ratio+resolution_p",
        "extra_defaults": {"resolution": "1080p"},
    },
    "KlingOmniReferenceToVideo_fal": {
        "output": "STRING",
        "duration_param": "duration",
        "duration_format": "str",
        "size_param": "aspect_ratio",
        "extra_defaults": {},
    },
    "MiniMaxSubjectReference_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "needs_image": True,
        "image_param": "subject_reference_image",
        "extra_defaults": {"prompt_optimizer": True},
    },
    "MiniMaxTextToVideo_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "extra_defaults": {"prompt_optimizer": True},
    },
    "KreaWan14bVideoToVideo_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "extra_defaults": {},
    },
    "WanVACEVideoEdit_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "extra_defaults": {},
    },
    "KlingOmniVideoToVideoEdit_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "extra_defaults": {},
    },
    "Krea_Wan14b_VideoToVideo_fal": {
        "output": "STRING",
        "duration_param": None,
        "size_param": None,
        "extra_defaults": {},
    },
    # --- Native ComfyUI API nodes (output VIDEO, routed via comfy-api-liberation) ---
    # These nodes call providers DIRECTLY (not fal.ai). They output VIDEO type
    # which is compatible with SaveVideo. comfy-api-liberation intercepts the
    # proxy URLs and routes to the provider with our API keys.
    "ByteDanceImageToVideoNode": {
        "output": "VIDEO",
        "duration_param": "duration",
        "duration_format": "int",  # INT slider 3-12
        "size_param": "resolution_p+aspect_ratio",
        "needs_image": True,
        "image_param": "image",
        "model_param": "model",
        "model_default": "seedance-1-0-pro-fast-251015",
        "extra_defaults": {
            "aspect_ratio": "16:9",
            "seed": 0,
            "camera_fixed": False,
            "watermark": False,
        },
    },
    "ByteDanceTextToVideoNode": {
        "output": "VIDEO",
        "duration_param": "duration",
        "duration_format": "int",
        "size_param": "resolution_p+aspect_ratio",
        "model_param": "model",
        "model_default": "seedance-1-0-pro-fast-251015",
        "extra_defaults": {
            "aspect_ratio": "16:9",
            "seed": 0,
            "camera_fixed": False,
            "watermark": False,
        },
    },
    "KlingImage2VideoNode": {
        "output": "VIDEO",
        "duration_param": "duration",
        "duration_format": "int",
        "size_param": None,
        "needs_image": True,
        "image_param": "image",
        "extra_defaults": {},
    },
    "KlingTextToVideoNode": {
        "output": "VIDEO",
        "duration_param": "duration",
        "duration_format": "int",
        "size_param": None,
        "extra_defaults": {},
    },
}


# Node → fal.ai API endpoint mapping (from ComfyUI-fal-API source code)
_FAL_ENDPOINTS: dict[str, str] = {
    "SeedanceTextToVideo_fal": "fal-ai/bytedance/seedance/v1/lite/text-to-video",
    "SeedanceImageToVideo_fal": "fal-ai/bytedance/seedance/v1/lite/image-to-video",
    "Kling25TurboPro_fal": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "Kling26Pro_fal": "fal-ai/kling-video/v2.6/pro/text-to-video",
    "KlingMaster_fal": "fal-ai/kling-video/v2/master/text-to-video",
    "Kling21Pro_fal": "fal-ai/kling-video/v2.1/pro/image-to-video",
    "Veo3_fal": "fal-ai/veo3",
    "Veo31_fal": "fal-ai/veo3.1/image-to-video",
    "Veo31Fast_fal": "fal-ai/veo3.1/fast/image-to-video",
    "Veo2ImageToVideo_fal": "fal-ai/veo2/image-to-video",
    "LumaDreamMachine_fal": "fal-ai/luma-dream-machine/ray-2",
    "RunwayGen3_fal": "fal-ai/runway-gen3/turbo/image-to-video",
    "Sora2Pro_fal": "fal-ai/sora-2/image-to-video/pro",
    "WanPro_fal": "fal-ai/wan-pro/image-to-video",
    "Wan25_preview_fal": "fal-ai/wan-25-preview/image-to-video",
    "Wan26_fal": "fal-ai/wan/v2.6/text-to-video",
    "KlingOmniReferenceToVideo_fal": "fal-ai/kling-video/o1/reference-to-video",
    "MiniMaxSubjectReference_fal": "fal-ai/minimax/video-01-subject-reference",
    "MiniMaxTextToVideo_fal": "fal-ai/minimax/video-01/text-to-video",
    "KreaWan14bVideoToVideo_fal": "fal-ai/krea/wan-14b-v2v",
    "Krea_Wan14b_VideoToVideo_fal": "fal-ai/krea/wan-14b-v2v",
    "WanVACEVideoEdit_fal": "fal-ai/wan-vace/video-edit",
    "KlingOmniVideoToVideoEdit_fal": "fal-ai/kling-video/o1/video-to-video/edit",
}


async def _fal_direct_submit(
    endpoint: str,
    inputs: dict[str, Any],
    timeout_s: int = 600,
) -> dict[str, Any]:
    """Call fal.ai REST API directly (bypass ComfyUI for video nodes).

    fal.ai queue API: POST /fal/queue/submit → GET /fal/queue/requests/{id}/status
    Returns {"video_url": "...", "status": "completed"} or {"error": "..."}.
    """
    if not FAL_API_KEY:
        return {"error": "FAL_API_KEY not configured"}

    fal_base = "https://queue.fal.run"
    headers = {"Authorization": f"Key {FAL_API_KEY}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            # Submit to queue
            async with session.post(
                f"{fal_base}/{endpoint}",
                headers=headers,
                json=inputs,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    print(f"[fal] Submit error {resp.status}: {body[:200]}", flush=True)
                    return {"error": f"fal.ai {resp.status}: {body[:300]}"}
                data = await resp.json()
                print(f"[fal] Submit OK: keys={list(data.keys())[:8]}", flush=True)

            # If response has video URL directly (sync mode)
            if data.get("video", {}).get("url"):
                return {"status": "completed", "video_url": data["video"]["url"]}

            # Queue mode: poll for result
            request_id = data.get("request_id", "")
            status_url = data.get("status_url", "")
            response_url = data.get("response_url", "")

            if not request_id and not status_url:
                # Direct response (not queued)
                print(f"[fal] No queue id — checking direct response", flush=True)
                video = data.get("video", {})
                if isinstance(video, dict) and video.get("url"):
                    return {"status": "completed", "video_url": video["url"]}
                # Check for list of videos
                videos = data.get("videos", [])
                if videos and isinstance(videos[0], dict):
                    return {"status": "completed", "video_url": videos[0].get("url", "")}
                print(f"[fal] WARNING: no video_url in direct response: {json.dumps(data)[:300]}", flush=True)
                return {"status": "completed", "raw": data}

            # Poll status_url
            poll_url = status_url or f"{fal_base}/{endpoint}/requests/{request_id}/status"
            # Use response_url from fal.ai as-is — it works for most providers
            # (Seedance, Veo, Kling, etc.) but may fail for MiniMax.
            result_url = response_url or f"{fal_base}/{endpoint}/requests/{request_id}"
            print(f"[fal] Queue: id={request_id[:16]} result_url={result_url[:80]}", flush=True)

            for poll_i in range(timeout_s // 5):
                await asyncio.sleep(5)
                try:
                    async with session.get(
                        poll_url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as poll_resp:
                        poll_data = await poll_resp.json()
                        status = poll_data.get("status", "")
                        if poll_i % 6 == 0:  # Log every 30s
                            print(f"[fal] Poll {poll_i}: {status} url={poll_url[:80]}", flush=True)
                        if status == "COMPLETED":
                            # Fetch result — try response_url, then
                            # updated response_url from poll if different
                            poll_result_url = poll_data.get("response_url", "")
                            urls_to_try = [result_url]
                            if poll_result_url and poll_result_url != result_url:
                                urls_to_try.insert(0, poll_result_url)

                            for try_url in urls_to_try:
                                try:
                                    async with session.get(
                                        try_url, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=30),
                                    ) as res_resp:
                                        if res_resp.status != 200:
                                            print(f"[fal] Result {res_resp.status} from {try_url[:80]}", flush=True)
                                            continue
                                        result = await res_resp.json(content_type=None)
                                except Exception as fetch_err:
                                    print(f"[fal] Result fetch error: {fetch_err}", flush=True)
                                    continue

                                video = result.get("video", {})
                                if isinstance(video, dict) and video.get("url"):
                                    print(f"[fal] Got video URL ({len(video['url'])} chars)", flush=True)
                                    return {"status": "completed", "video_url": video["url"]}
                                videos = result.get("videos", [])
                                if videos:
                                    urls = [v.get("url", "") for v in videos if isinstance(v, dict)]
                                    if urls:
                                        print(f"[fal] Got {len(urls)} video URLs", flush=True)
                                        return {"status": "completed", "video_url": urls[0], "video_urls": urls}
                                # If got 200 but no video URL, return raw
                                return {"status": "completed", "raw": result}

                            return {"status": "error", "error": "All result URLs failed"}
                        if status == "FAILED":
                            return {"status": "error", "error": str(poll_data.get("error", ""))[:300]}
                except Exception:
                    continue

            return {"status": "timeout"}
    except Exception as exc:
        return {"error": f"fal.ai direct call failed: {exc}"}


async def _byteplus_generate_video(
    prompt: str,
    reference_image: str = "",
    duration: int = 5,
    resolution: str = "720p",
    seed: int = -1,
    timeout_s: int = 600,
) -> dict[str, Any]:
    """Call BytePlus Seedance API directly (cheaper than fal.ai).

    BytePlus API: POST /seedance/v1/videos → GET /seedance/v1/videos/{job_id}
    Returns {"video_url": "...", "status": "completed"} or {"error": "..."}.
    ~60% cheaper than fal.ai for the same Seedance model.
    """
    if not BYTEPLUS_API_KEY:
        return {"error": "BYTEPLUS_API_KEY not configured"}

    base_url = "https://api.byteplus.com/seedance/v1"
    headers = {
        "Authorization": f"Bearer {BYTEPLUS_API_KEY}",
        "Content-Type": "application/json",
    }

    body: dict[str, Any] = {
        "model": "seedance-2.0",
        "prompt": prompt,
        "resolution": resolution,
        "duration": duration,
        "aspect_ratio": "16:9",
    }
    if seed >= 0:
        body["seed"] = seed

    # Image-to-video: add reference image
    if reference_image:
        body["references"] = [{
            "type": "image",
            "data": reference_image,  # base64 data URI or URL
            "role": "subject",
        }]

    try:
        async with aiohttp.ClientSession() as session:
            # Submit generation
            async with session.post(
                f"{base_url}/videos",
                headers=headers,
                json=body,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status not in (200, 201, 202):
                    err_body = await resp.text()
                    print(f"[byteplus] Submit error {resp.status}: {err_body[:200]}", flush=True)
                    return {"error": f"BytePlus {resp.status}: {err_body[:300]}"}
                data = await resp.json()

            job_id = data.get("id", data.get("task_id", ""))
            if not job_id:
                # Synchronous response with video
                video_url = data.get("output", {}).get("video_url", "")
                if video_url:
                    return {"status": "completed", "video_url": video_url}
                return {"error": f"No job_id in response: {json.dumps(data)[:200]}"}

            print(f"[byteplus] Job submitted: {job_id}", flush=True)

            # Poll for completion
            for poll_i in range(timeout_s // 5):
                await asyncio.sleep(5)
                try:
                    async with session.get(
                        f"{base_url}/videos/{job_id}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as poll_resp:
                        poll_data = await poll_resp.json()
                        status = poll_data.get("status", "").lower()
                        if poll_i % 6 == 0:
                            print(f"[byteplus] Poll {poll_i}: {status}", flush=True)
                        if status in ("completed", "succeed", "done"):
                            video_url = (
                                poll_data.get("output", {}).get("video_url", "")
                                or poll_data.get("video_url", "")
                                or poll_data.get("result", {}).get("video_url", "")
                            )
                            if video_url:
                                print(f"[byteplus] Video ready: {len(video_url)} chars", flush=True)
                                return {"status": "completed", "video_url": video_url}
                            return {"status": "completed", "raw": poll_data}
                        if status in ("failed", "error"):
                            return {"error": str(poll_data.get("error", poll_data.get("message", "")))[:300]}
                except Exception:
                    continue

            return {"status": "timeout", "error": f"BytePlus timeout after {timeout_s}s"}
    except Exception as exc:
        return {"error": f"BytePlus call failed: {exc}"}


# Seedance nodes that can be routed to BytePlus directly
_BYTEPLUS_SEEDANCE_NODES = {"SeedanceTextToVideo_fal", "SeedanceImageToVideo_fal"}


def _format_duration(seconds: int, fmt: str, values: list[str] | None = None) -> str | int:
    """Format duration for the specific node's expected format."""
    if fmt == "int":
        return seconds
    if fmt == "str_s":
        candidate = f"{seconds}s"
        if values and candidate not in values:
            return values[-1]  # use longest available
        return candidate
    # default: str
    return str(seconds)


def _resolve_image_size_preset(width: int, height: int) -> str:
    """Map pixel dimensions to ComfyUI fal image_size preset."""
    ratio = width / height if height > 0 else 1.0
    if ratio > 1.5:
        return "landscape_16_9"
    if ratio > 1.2:
        return "landscape_4_3"
    if ratio > 0.85:
        return "square_hd"
    if ratio > 0.65:
        return "portrait_4_3"
    return "portrait_16_9"


async def _composer_build_workflow(
    model: dict[str, Any],
    prompt: str,
    negative: str = "",
    width: int = 1024,
    height: int = 1024,
    style: str = "",
    camera: str = "",
    lens: str = "",
    reference_image: str = "",
    fps: int = 24,
    duration: int = 5,
) -> dict[str, Any]:
    """Build a ComfyUI workflow JSON for the selected model.

    Uses _FAL_NODE_SPECS to set correct parameters per node.
    Image nodes (return IMAGE) get SaveImage chained.
    Video nodes (return STRING/URL) do NOT get SaveImage.
    """
    node_name = model.get("node", "")

    # fal.ai nodes AND native API nodes (both registered in _FAL_NODE_SPECS)
    if node_name.endswith("_fal") or node_name in _FAL_NODE_SPECS:
        spec = _FAL_NODE_SPECS.get(node_name, {})
        output_type = spec.get("output", "IMAGE")
        is_video = output_type in ("STRING", "VIDEO")

        workflow: dict[str, Any] = {"prompt": {}}

        # Inject camera tokens into prompt
        full_prompt = _inject_camera_tokens(prompt, camera, lens)
        if style:
            full_prompt = f"{full_prompt}, {style}"

        # Start with prompt + any node-specific defaults
        inputs: dict[str, Any] = {"prompt": full_prompt}
        for k, v in spec.get("extra_defaults", {}).items():
            inputs[k] = v

        # Model selection for native nodes (COMBO input)
        model_param = spec.get("model_param")
        if model_param:
            inputs[model_param] = spec.get("model_default", "")

        # --- Size params (varies per node) ---
        size_param = spec.get("size_param", "")
        if size_param:
            ar = _resolve_aspect_ratio(width, height)
            if "aspect_ratio" in size_param:
                inputs["aspect_ratio"] = ar
            if "resolution_p" in size_param:
                # "480p", "720p", "1080p" format
                if max(width, height) >= 1920:
                    inputs["resolution"] = "1080p"
                elif max(width, height) >= 1280:
                    inputs["resolution"] = "720p"
                else:
                    inputs["resolution"] = "480p"
            if size_param == "image_size":
                inputs["image_size"] = _resolve_image_size_preset(width, height)
            elif size_param == "image_size_wxh":
                # GPTImage format: "1024x1024", "1536x1024", "1024x1536"
                if width > height:
                    inputs["image_size"] = "1536x1024"
                elif height > width:
                    inputs["image_size"] = "1024x1536"
                else:
                    inputs["image_size"] = "1024x1024"
            elif size_param == "image_size_preset":
                inputs["image_size"] = _resolve_image_size_preset(width, height)
            elif "resolution" in size_param and "aspect_ratio" not in size_param:
                pass  # already handled above

        # --- Duration (video nodes only) ---
        dur_param = spec.get("duration_param")
        if dur_param and is_video:
            dur_fmt = spec.get("duration_format", "str")
            dur_values = spec.get("duration_values")
            inputs[dur_param] = _format_duration(duration, dur_fmt, dur_values)

        # --- Negative prompt (image nodes that accept it) ---
        if negative and not is_video:
            inputs["negative_prompt"] = negative

        # --- Reference image ---
        # ComfyUI nodes expect IMAGE tensor input, not URLs.
        # Copy image to ComfyUI input dir + add LoadImage node.
        load_image_node_id = None
        if reference_image and spec.get("needs_image"):
            img_param = spec.get("image_param", "image")
            ref_path = Path(reference_image) if not reference_image.startswith("data:") else None

            if ref_path and ref_path.exists():
                # Copy to ComfyUI input directory
                import shutil
                comfyui_input = Path(COMFYUI_DIR)
                comfyui_input.mkdir(parents=True, exist_ok=True)
                dest = comfyui_input / ref_path.name
                shutil.copy2(str(ref_path), str(dest))
                # Add LoadImage node and connect to video node
                load_image_node_id = "load_ref"
                workflow["prompt"][load_image_node_id] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": ref_path.name},
                }
                inputs[img_param] = [load_image_node_id, 0]
                print(f"[composer] LoadImage: {ref_path.name} → {img_param}", flush=True)
            elif reference_image.startswith("data:"):
                # Data URI: decode to file, then LoadImage
                try:
                    header, b64data = reference_image.split(",", 1)
                    ext = "png" if "png" in header else "jpg"
                    fname = f"ref_{hash(b64data[:50]) % 99999:05d}.{ext}"
                    comfyui_input = Path(COMFYUI_DIR)
                    comfyui_input.mkdir(parents=True, exist_ok=True)
                    dest = comfyui_input / fname
                    dest.write_bytes(base64.b64decode(b64data))
                    load_image_node_id = "load_ref"
                    workflow["prompt"][load_image_node_id] = {
                        "class_type": "LoadImage",
                        "inputs": {"image": fname},
                    }
                    inputs[img_param] = [load_image_node_id, 0]
                    print(f"[composer] LoadImage (from data URI): {fname} → {img_param}", flush=True)
                except Exception as b64_exc:
                    print(f"[composer] Data URI decode error: {b64_exc}", flush=True)
                    # Fallback: pass URL directly (fal.ai nodes may accept URLs)
                    inputs[img_param] = reference_image

        # Build node 1 (generator)
        workflow["prompt"]["1"] = {
            "class_type": node_name,
            "inputs": inputs,
        }

        # Node 2: SaveImage ONLY for IMAGE nodes (not video)
        if not is_video:
            workflow["prompt"]["2"] = {
                "class_type": "SaveImage",
                "inputs": {"images": ["1", 0], "filename_prefix": "composer"},
            }
        # VIDEO output nodes (native): add SaveVideo for ComfyUI to persist
        # SaveVideo requires codec + format inputs (ComfyUI validation)
        if output_type == "VIDEO":
            workflow["prompt"]["save_video"] = {
                "class_type": "SaveVideo",
                "inputs": {
                    "video": ["1", 0],
                    "filename_prefix": "composer_video",
                    "codec": "h264",
                    "format": "mp4",
                },
            }
        # STRING video nodes (fal.ai): no output node — handled by bypass in _composer_submit

        workflow["_metadata"] = {
            "composer": True,
            "model": model.get("name", node_name),
            "output_type": output_type,
            "task": model.get("tasks", []),
            "budget": model.get("budget", "?"),
            "cost": model.get("cost", model.get("cost_per_sec", 0)),
        }
        return workflow

    # Local nodes (KSampler, AnimateDiff, etc.) — use template-based approach
    return _build_local_workflow(prompt, negative, width, height, style)


def _build_local_workflow(
    prompt: str, negative: str, width: int, height: int, style: str,
) -> dict[str, Any]:
    """Fallback: build a local KSampler workflow."""
    full_prompt = f"{prompt}, {style}" if style else prompt
    return {
        "prompt": {
            "1": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"}},
            "2": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": min(width, 1024), "height": min(height, 1024),
                             "batch_size": 1}},
            "3": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": full_prompt, "clip": ["1", 1]}},
            "4": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": negative or "blurry, low quality", "clip": ["1", 1]}},
            "5": {"class_type": "KSampler",
                  "inputs": {"model": ["1", 0], "seed": 42, "steps": 20, "cfg": 7.5,
                             "sampler_name": "euler_ancestral", "scheduler": "karras",
                             "positive": ["3", 0], "negative": ["4", 0],
                             "latent_image": ["2", 0], "denoise": 1.0}},
            "6": {"class_type": "VAEDecode",
                  "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0], "filename_prefix": "composer_local"}},
        },
        "_metadata": {"composer": True, "model": "local_ksampler", "budget": "eco"},
    }


async def _comfyui_validate_workflow(
    workflow: dict[str, Any],
) -> dict[str, Any]:
    """Submit workflow to ComfyUI /prompt for graph validation only.

    If ComfyUI returns 200 (graph valid), immediately cancel the queued prompt
    to avoid actual generation. Returns {"status": "validated", "valid": true}
    or {"status": "error", "valid": false, "error": "..."}.
    """
    if not COMFYUI_API_URL:
        return {"status": "skipped", "valid": True, "note": "COMFYUI_API_URL not configured"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{COMFYUI_API_URL}/prompt",
                json={"prompt": workflow.get("prompt", workflow)},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[dry-run] ComfyUI validation FAILED {resp.status}: {body[:400]}", flush=True)
                    return {"status": "error", "valid": False, "error": body[:600]}
                data = await resp.json()
                prompt_id = data.get("prompt_id", "")
                print(f"[dry-run] ComfyUI graph VALID (prompt_id={prompt_id})", flush=True)

            # Cancel the queued prompt immediately to avoid generation
            if prompt_id:
                try:
                    async with session.post(
                        f"{COMFYUI_API_URL}/queue",
                        json={"delete": [prompt_id]},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as cancel_resp:
                        print(f"[dry-run] Queue cancel: {cancel_resp.status}", flush=True)
                except Exception:
                    pass  # Best-effort cancel

        return {"status": "validated", "valid": True, "prompt_id": prompt_id}
    except Exception as exc:
        print(f"[dry-run] ComfyUI validation error: {exc}", flush=True)
        return {"status": "error", "valid": False, "error": str(exc)}


def _fal_submit_mock(scene_index: int = 0) -> dict[str, Any]:
    """Mock fal.ai response for dry-run mode. Zero cost, zero latency."""
    return {
        "status": "completed",
        "video_url": f"https://dry-run.local/mock_scene_{scene_index}.mp4",
        "video_urls": [f"https://dry-run.local/mock_scene_{scene_index}.mp4"],
        "dry_run": True,
        "images": [],
    }


async def _composer_submit(
    workflow: dict[str, Any], wait: bool = True, timeout_s: int = 180,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Submit a workflow to ComfyUI /prompt API, optionally wait for result.

    Handles both IMAGE outputs (images[]) and STRING outputs (video URLs).
    Returns {"status": "completed", "prompt_id": ..., "images": [...], "video_urls": [...]}.
    """
    # --- Dry-run: validate workflow only, cancel immediately ---
    if dry_run:
        return await _comfyui_validate_workflow(workflow)
    is_video = workflow.get("_metadata", {}).get("output_type") == "STRING"

    # VIDEO nodes (STRING output): call fal.ai directly.
    # ComfyUI cannot handle STRING-only nodes (prompt_no_outputs error).
    # IMAGE nodes: go through ComfyUI /prompt API normally.
    # NOTE: When comfy-api-liberation + native VIDEO nodes (output VIDEO)
    # are fully wired, this bypass can be removed.
    if is_video and FAL_API_KEY:
        prompt_nodes = workflow.get("prompt", {})
        for nid, node in prompt_nodes.items():
            class_type = node.get("class_type", "")
            if class_type in _FAL_ENDPOINTS:
                endpoint = _FAL_ENDPOINTS[class_type]
                inputs = dict(node.get("inputs", {}))
                # Convert ComfyUI LoadImage refs to fal.ai image URLs
                for k, v in list(inputs.items()):
                    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                        ref_node_id = v[0]
                        ref_node = prompt_nodes.get(ref_node_id, {})
                        if ref_node.get("class_type") == "LoadImage":
                            img_name = ref_node.get("inputs", {}).get("image", "")
                            if img_name:
                                # Find image in ComfyUI input dir and convert to data URI
                                comfyui_input = Path(COMFYUI_DIR) / img_name
                                if comfyui_input.exists():
                                    # Upload to fal.ai storage for a proper URL
                                    img_url = await _upload_to_fal_storage(str(comfyui_input))
                                    if not img_url:
                                        # Fallback to data URI
                                        img_url = _image_to_fal_url(str(comfyui_input))
                                    if img_url:
                                        inputs[k] = img_url
                                        is_data = "data:" in img_url[:10]
                                        print(f"[composer] Ref image → {'data URI' if is_data else 'fal CDN'} for {k}", flush=True)
                                        continue
                        inputs.pop(k)  # Remove unresolvable node refs
                print(f"[composer] Video {class_type} → fal.ai: {endpoint}", flush=True)
                fal_result = await _fal_direct_submit(endpoint, inputs, timeout_s=timeout_s)
                video_url = fal_result.get("video_url", "")
                if video_url:
                    return {
                        "status": "completed",
                        "video_urls": [video_url],
                        "images": [],
                        "provider": "fal.ai",
                    }
                return {
                    "status": fal_result.get("status", "error"),
                    "error": fal_result.get("error", "No video URL"),
                    "video_urls": [],
                    "images": [],
                }

    try:
        async with aiohttp.ClientSession() as session:
            # Queue the prompt
            async with session.post(
                f"{COMFYUI_API_URL}/prompt",
                json={"prompt": workflow.get("prompt", workflow)},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[composer] ComfyUI submit error {resp.status}: {body[:600]}", flush=True)
                    return {"error": f"ComfyUI {resp.status}: {body[:600]}"}
                data = await resp.json()
                prompt_id = data.get("prompt_id", "")
                print(f"[composer] Submitted to ComfyUI: prompt_id={prompt_id}", flush=True)

            if not wait or not prompt_id:
                return {"status": "queued", "prompt_id": prompt_id}

            # Poll /history/{prompt_id} until complete
            for _ in range(timeout_s // 3):
                await asyncio.sleep(3)
                try:
                    async with session.get(
                        f"{COMFYUI_API_URL}/history/{prompt_id}",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as hist_resp:
                        if hist_resp.status != 200:
                            continue
                        history = await hist_resp.json()
                        if prompt_id not in history:
                            continue
                        entry = history[prompt_id]
                        status = entry.get("status", {})
                        if status.get("completed", False):
                            images: list[dict[str, Any]] = []
                            video_urls: list[str] = []

                            for node_id, outputs in entry.get("outputs", {}).items():
                                # IMAGE outputs (SaveImage nodes)
                                for img in outputs.get("images", []):
                                    images.append({
                                        "filename": img.get("filename", ""),
                                        "subfolder": img.get("subfolder", ""),
                                        "type": img.get("type", "output"),
                                    })
                                # STRING outputs (video URL nodes)
                                for text_val in outputs.get("text", []):
                                    if isinstance(text_val, str) and (
                                        text_val.startswith("http") or text_val.startswith("/")
                                    ):
                                        video_urls.append(text_val)
                                # Also check "string" key (some nodes)
                                for str_val in outputs.get("string", []):
                                    if isinstance(str_val, str) and str_val.startswith("http"):
                                        video_urls.append(str_val)

                            result: dict[str, Any] = {
                                "status": "completed",
                                "prompt_id": prompt_id,
                                "images": images,
                            }
                            if video_urls:
                                result["video_urls"] = video_urls
                            return result

                        if status.get("status_str") == "error":
                            return {
                                "status": "error",
                                "prompt_id": prompt_id,
                                "error": str(status.get("messages", ""))[:300],
                            }
                except Exception:
                    continue

            return {"status": "timeout", "prompt_id": prompt_id}
    except Exception as exc:
        return {"error": f"ComfyUI submit failed: {exc}"}


async def _composer_download_image(
    image_info: dict[str, Any],
) -> bytes | None:
    """Download a generated image from ComfyUI /view endpoint."""
    filename = image_info.get("filename", "")
    subfolder = image_info.get("subfolder", "")
    img_type = image_info.get("type", "output")
    if not filename:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            params = {"filename": filename, "subfolder": subfolder, "type": img_type}
            async with session.get(
                f"{COMFYUI_API_URL}/view",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


async def _composer_download_video(url: str) -> bytes | None:
    """Download a video from a fal.ai URL. Returns video bytes."""
    if not url or not url.startswith("http"):
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


def _image_to_fal_url(image_path: str) -> str:
    """Convert a local image file to a base64 data URI for fal.ai.

    fal.ai accepts data URIs directly in JSON parameters.
    This avoids the need for a public CDN or fal.ai storage upload.
    """
    path = Path(image_path)
    if not path.exists():
        return ""
    img_bytes = path.read_bytes()
    # Skip if image is too large (>10MB — use _upload_to_fal_storage instead)
    if len(img_bytes) > 10 * 1024 * 1024:
        return ""
    ext = path.suffix.lower().lstrip(".")
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }
    mime = mime_map.get(ext, "image/png")
    b64 = base64.b64encode(img_bytes).decode()
    return f"data:{mime};base64,{b64}"


async def _upload_to_fal_storage(image_path: str) -> str:
    """Upload image to fal.ai storage CDN, return public URL.

    Fallback for images >10MB that cannot use data URIs.
    Uses fal.ai's file upload endpoint.
    """
    if not FAL_API_KEY:
        return ""
    path = Path(image_path)
    if not path.exists():
        return ""
    try:
        headers = {"Authorization": f"Key {FAL_API_KEY}"}
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field(
                "file",
                path.read_bytes(),
                filename=path.name,
                content_type="image/png",
            )
            async with session.post(
                "https://fal.ai/api/storage/upload",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("url", result.get("access_url", ""))
    except Exception as exc:
        print(f"[fal-upload] Error: {exc}", flush=True)
    return ""


async def _get_fal_image_url(image_path: str) -> str:
    """Get a fal.ai-compatible URL for a local image.

    Tries base64 data URI first (fastest, no network).
    Falls back to fal.ai storage upload for large images.
    """
    url = _image_to_fal_url(image_path)
    if url:
        return url
    return await _upload_to_fal_storage(image_path)


def _generate_asset_name(analysis: dict[str, Any], filename: str = "") -> str:
    """Generate a short, descriptive asset name from analysis.

    Pattern: Subject-Style-Mood (max 40 chars)
    Examples: Shoes-3D-Playful, Dragon-Fantasy-Dramatic, Village-Ghibli-Nostalgic
    """
    style = analysis.get("style", "")
    mood = analysis.get("mood", "")
    prompt = analysis.get("suggested_prompt", analysis.get("ai_prompt", ""))

    # Extract subject from prompt (first noun phrase, ~1-2 words)
    subject = ""
    if prompt:
        # Take first 2-3 meaningful words from prompt
        words = [w for w in prompt.split()[:6]
                 if len(w) > 2 and w.lower() not in
                 {"the", "and", "with", "from", "that", "this", "for",
                  "create", "generate", "make", "design", "draw", "render",
                  "beautiful", "stunning", "amazing", "realistic", "high",
                  "quality", "detailed", "professional"}]
        subject = " ".join(words[:2]).title()

    if not subject and filename:
        # Fallback: clean filename
        subject = Path(filename).stem.split("[")[0].split("-")[0].strip()[:15]

    if not subject:
        subject = "Scene"

    # Shorten style to 1-2 words
    style_short = style.split(",")[0].strip()[:15] if style else ""
    mood_short = mood.split(",")[0].strip()[:12] if mood else ""

    parts = [p for p in [subject[:15], style_short, mood_short] if p]
    name = "-".join(parts)

    # Clean and limit
    name = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip("-")[:40]
    return name or "Untitled"


# ============================================================
# 17. Production step handlers
# ============================================================
async def _step_brief(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle brief step: store description + specs, create Kitsu project.

    params can override: fps, format, resolution, style, production_type
    """
    description = params.get("description", job.get("title", ""))

    # Allow brief to set/override technical specs
    fps = params.get("fps", job.get("fps", "24"))
    fmt = params.get("format", job.get("format", "landscape"))
    style = params.get("style", job.get("style", "2d3d"))
    prod_type = params.get("production_type", "tvshow")

    # Resolve resolution from format preset or explicit param
    if "resolution" in params:
        resolution = params["resolution"]
    else:
        preset = RESOLUTION_PRESETS.get(fmt, RESOLUTION_PRESETS["landscape"])
        resolution = preset["resolution"]

    extras: dict[str, Any] = {
        "description": description,
        "fps": fps,
        "format": fmt,
        "resolution": resolution,
        "style": style,
    }

    kitsu_result: dict[str, Any] = {}
    if KITSU_URL and KITSU_TOKEN:
        try:
            async with aiohttp.ClientSession() as session:
                # Create a NEW Kitsu project for this production job
                project = await _kitsu_create_project(
                    session, job["title"], prod_type,
                )
                # Update project with technical specs from brief
                await _kitsu_api(
                    session, "PUT",
                    f"/data/projects/{project['id']}",
                    json_body={
                        "fps": fps,
                        "resolution": resolution,
                        "production_style": style,
                    },
                )
                project_id = project["id"]

                # Add ALL persons to team (admin + bot)
                try:
                    persons = await _kitsu_api(
                        session, "GET", "/data/persons",
                    )
                    for person in persons:
                        try:
                            await _kitsu_api(
                                session, "POST",
                                f"/data/projects/{project_id}/team",
                                json_body={"person_id": person["id"]},
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                # Create main sequence + first shot inside the new project
                seq = await _kitsu_create_sequence(
                    session, project_id, "", job["title"][:80],
                )
                # Create an overview shot (task types are for_entity=Shot)
                shot = await _kitsu_create_shot(
                    session, project_id, seq["id"], "",
                    "SH0000", {"note": "Overview shot for pipeline tasks"},
                )
                extras["kitsu_project_id"] = project_id
                extras["kitsu_sequence_id"] = seq["id"]
                extras["kitsu_overview_shot_id"] = shot["id"]

                # Create Brief task on the overview shot + mark done
                task_type_id = await _kitsu_get_task_type_id(session, "Brief")
                task = await _kitsu_get_or_create_task(
                    session, shot["id"], task_type_id, project_id,
                )
                done_id = await _kitsu_get_done_status_id(session)
                await _kitsu_post_comment(
                    session, task["id"], done_id, f"Brief: {description}",
                )

                # Create a Concept entity for the brief (visible in Concepts tab)
                concept_result = await _kitsu_api(
                    session, "POST",
                    f"/data/projects/{project_id}/concepts",
                    json_body={
                        "name": f"Brief — {job['title'][:60]}",
                        "description": (
                            f"{description}\n\n"
                            f"Camera: {job.get('camera', 'N/A')}\n"
                            f"Lens: {job.get('lens', 'N/A')}\n"
                            f"FPS: {fps}\n"
                            f"Resolution: {resolution}\n"
                            f"Style: {style}"
                        ),
                        "data": {
                            "type": "brief",
                            "camera": job.get("camera", ""),
                            "lens": job.get("lens", ""),
                            "fps": fps,
                            "resolution": resolution,
                            "style": style,
                        },
                    },
                )
                concept_id = concept_result.get("id", "") if concept_result else ""

                # Mood board image is generated later in _step_research
                # (needs video ref analysis for accurate style/colors)

                kitsu_result = {
                    "project_id": project_id,
                    "project_name": job["title"],
                    "task_id": task["id"],
                    "concept_id": concept_id,
                    "status": "done",
                }
        except Exception as exc:
            kitsu_result = {"error": str(exc)}

    # Persist concept_id in job for research step to use
    if kitsu_result.get("concept_id"):
        extras["concept_id"] = kitsu_result["concept_id"]

    # Send Telegram notification
    await _notify_step_completed(job, "brief")

    return {"status": "ok", "description": description, "kitsu": kitsu_result}, extras


async def _call_gemini_direct(prompt: str, max_tokens: int = 3000) -> str:
    """Call Google Gemini API directly (bypass LiteLLM budget).

    Used as fallback when LiteLLM returns 429 (budget exceeded).
    """
    if not GOOGLE_API_KEY:
        return ""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
                },
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[gemini-direct] Failed: {resp.status} {body[:200]}", flush=True)
                    return ""
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return ""
    except Exception as exc:
        print(f"[gemini-direct] Error: {exc}", flush=True)
        return ""


async def _download_metube_video(url: str, watch_dir: Path) -> Path | None:
    """Download video from MeTube (tube.ewutelo.cloud) into watch_dir.

    Returns local path if successful, None otherwise.
    """
    from urllib.parse import unquote
    filename = unquote(url.split("/")[-1])
    if not filename:
        return None

    local_path = watch_dir / filename
    if local_path.exists() and local_path.stat().st_size > 0:
        print(f"[research] MeTube video already in watch: {local_path.name}", flush=True)
        return local_path

    print(f"[research] Downloading MeTube video: {filename}...", flush=True)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    print(f"[research] MeTube download failed: {resp.status}", flush=True)
                    return None
                content = await resp.read()
                if len(content) > 500 * 1024 * 1024:
                    print(f"[research] Video too large: {len(content)} bytes", flush=True)
                    return None
                local_path.write_bytes(content)
                print(f"[research] Downloaded {len(content)} bytes -> {local_path.name}", flush=True)
                return local_path
    except Exception as exc:
        print(f"[research] MeTube download error: {exc}", flush=True)
        return None


def _scene_decomposition_prompt(
    description: str, num_scenes: int, style: str, mood: str, colors: str,
) -> str:
    """Build the scene decomposition prompt (shared by Claude CLI and LiteLLM)."""
    style_ctx = ""
    if style or mood or colors:
        style_ctx = f"\nStyle de reference: {style}\nMood: {mood}\nCouleurs: {colors}"
    return (
        f"Tu es un directeur artistique pour des videos courtes (reels/shorts).\n"
        f"Decompose ce brief en exactement {num_scenes} scenes cinematographiques.{style_ctx}\n\n"
        f"Brief: {description}\n\n"
        f"IMPORTANT: Chaque scene DOIT etre directement liee au brief ci-dessus. "
        f"Le sujet principal du brief doit apparaitre dans TOUTES les scenes. "
        f"Ne genere PAS de scenes sans rapport avec le brief.\n\n"
        f"Retourne UNIQUEMENT un JSON array valide. Pour chaque scene:\n"
        f'[{{"scene_index": 0, "description": "Description narrative (1-2 phrases)", '
        f'"visual_prompt": "Prompt detaille pour generation image/video en anglais, '
        f'incluant le sujet du brief, action, eclairage, ambiance, cadrage", '
        f'"camera_movement": "static | pan left | pan right | dolly in | dolly out | tracking | crane up | handheld", '
        f'"mood": "mot-cle ambiance", "duration_seconds": 5}}]'
    )


def _parse_llm_scenes(
    content: str, style: str, mood: str, colors: str,
) -> list[dict[str, Any]]:
    """Parse LLM response into scene_analyses format."""
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    content = content.strip()
    # Find first JSON array
    start = content.find("[")
    end = content.rfind("]") + 1
    if start >= 0 and end > start:
        content = content[start:end]

    scenes_raw = json.loads(content)
    scenes = []
    for i, s in enumerate(scenes_raw):
        scenes.append({
            "scene_index": i,
            "start_time": i * s.get("duration_seconds", 5),
            "end_time": (i + 1) * s.get("duration_seconds", 5),
            "duration": s.get("duration_seconds", 5),
            "analysis": {
                "style": style or "cinematic",
                "mood": s.get("mood", mood or "dramatic"),
                "colors": colors or "",
                "description": s.get("description", ""),
                "suggested_prompt": s.get("visual_prompt", s.get("description", "")),
                "camera_movement": s.get("camera_movement", "static"),
                "negative_prompt": "blurry, low quality, distorted",
            },
            "llm_generated": True,
        })
    return scenes


async def _claude_cli_decompose_scenes(
    description: str,
    num_scenes: int = 5,
    style: str = "",
    mood: str = "",
    colors: str = "",
) -> list[dict[str, Any]]:
    """Bridge to Claude Code CLI (Max OAuth, Opus 4.6) for scene decomposition.

    Uses `claude -p --dangerously-skip-permissions` in non-interactive mode.
    Returns list of scene dicts compatible with scene_analyses format.
    """
    import shutil
    cli = shutil.which("claude") or CLAUDE_CLI_PATH
    if not Path(cli).exists():
        print("[script] Claude CLI not found, skipping", flush=True)
        return []

    prompt = _scene_decomposition_prompt(description, num_scenes, style, mood, colors)

    try:
        proc = await asyncio.create_subprocess_exec(
            cli, "-p", prompt, "--dangerously-skip-permissions",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode().strip()
        if proc.returncode != 0:
            print(f"[script] Claude CLI error rc={proc.returncode}: {stderr.decode()[:200]}", flush=True)
            return []

        scenes = _parse_llm_scenes(output, style, mood, colors)
        print(f"[script] Claude CLI decomposed brief into {len(scenes)} scenes", flush=True)
        return scenes
    except asyncio.TimeoutError:
        print("[script] Claude CLI timeout (60s)", flush=True)
        return []
    except (json.JSONDecodeError, Exception) as exc:
        print(f"[script] Claude CLI parse error: {exc}", flush=True)
        return []


async def _llm_decompose_scenes(
    description: str,
    num_scenes: int = 5,
    style: str = "",
    mood: str = "",
    colors: str = "",
) -> list[dict[str, Any]]:
    """Fallback: use LiteLLM (claude-sonnet) for scene decomposition.

    Returns list of scene dicts compatible with scene_analyses format.
    Called when Claude CLI is not available and no scene_prompts provided.
    """
    if not LITELLM_URL or not LITELLM_API_KEY:
        return []

    prompt = _scene_decomposition_prompt(description, num_scenes, style, mood, colors)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/chat/completions",
                json={
                    "model": "claude-sonnet",
                    "messages": [
                        {"role": "system", "content": (
                            "Tu es un directeur artistique. Tu generes des scenes "
                            "cinematographiques STRICTEMENT liees au brief fourni. "
                            "Ne genere JAMAIS de contenu sans rapport avec le brief."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 3000,
                },
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status in (429, 400):
                    print(f"[script] LiteLLM {resp.status}, trying Gemini direct", flush=True)
                    content = await _call_gemini_direct(prompt, max_tokens=3000)
                    if not content:
                        return []
                elif resp.status != 200:
                    print(f"[script] LLM decompose failed: {resp.status}", flush=True)
                    return []
                else:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]

                return _parse_llm_scenes(content, style, mood, colors)
    except Exception as exc:
        print(f"[script] LLM decomposition error: {exc}", flush=True)
        return []


async def _llm_extract_entities(description: str) -> dict[str, list[str]]:
    """Extract characters, environments, props from a brief via LLM.

    Returns {"characters": [...], "environments": [...], "props": [...]}.
    """
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"characters": [], "environments": [], "props": []}

    prompt = (
        f"Extrais les entites visuelles de ce brief de video.\n"
        f"Retourne UNIQUEMENT un JSON valide avec ces 3 cles:\n"
        f'{{"characters": ["nom1", "nom2"], "environments": ["lieu1"], "props": ["objet1"]}}\n\n'
        f"Brief: {description}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/chat/completions",
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (429, 400):
                    print(f"[script] LiteLLM {resp.status}, trying Gemini direct for entities", flush=True)
                    content = await _call_gemini_direct(prompt, max_tokens=500)
                    if not content:
                        return {"characters": [], "environments": [], "props": []}
                elif resp.status != 200:
                    return {"characters": [], "environments": [], "props": []}
                else:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                if "```" in content:
                    content = (
                        content.split("```json")[-1].split("```")[0]
                        if "```json" in content
                        else content.split("```")[1].split("```")[0]
                    )
                result = json.loads(content.strip())
                print(f"[script] Entities: {sum(len(v) for v in result.values())} total", flush=True)
                return result
    except Exception as exc:
        print(f"[script] Entity extraction error: {exc}", flush=True)
        return {"characters": [], "environments": [], "props": []}


# --- Default artistic direction (fallback if LLM fails) ---
_DEFAULT_DIRECTION: dict[str, Any] = {
    "pacing": "medium",
    "defaultTransition": "crossfade",
    "defaultTransitionDurationFrames": 15,
    "colorGrade": {"preset": "none", "contrast": 1, "saturation": 1, "brightness": 1},
    "grain": 0,
    "typography": {"fontFamily": "Inter, sans-serif", "accentColor": "#3b82f6", "textColor": "#ffffff"},
    "subtitleStyle": "cinema",
}


async def _llm_artistic_direction(
    description: str,
    title: str,
    ref_style: str,
    ref_mood: str,
    ref_colors: str,
    scene_analyses: list[dict[str, Any]],
    camera: str,
    lens: str,
    video_format: str,
    num_scenes: int,
) -> dict[str, Any]:
    """Use LLM to decide artistic direction for Remotion montage.

    Exploits ALL metadata from research: style, mood, lighting, composition,
    color_grade, camera_movement, key_elements, narrative_arc.
    Returns ArtisticDirection dict (see Remotion Montage/types.ts).
    """
    if not LITELLM_URL or not LITELLM_API_KEY:
        return dict(_DEFAULT_DIRECTION)

    # Build rich context from scene analyses
    scenes_ctx = []
    for sa in scene_analyses:
        analysis = sa.get("analysis", sa)
        scenes_ctx.append({
            "lighting": analysis.get("lighting", ""),
            "composition": analysis.get("composition", ""),
            "color_grade": analysis.get("color_grade", ""),
            "camera_movement": analysis.get("camera_movement", ""),
            "key_elements": analysis.get("key_elements", []),
            "mood": analysis.get("mood", ""),
        })

    context_json = json.dumps({
        "brief": description,
        "title": title,
        "ref_style": ref_style,
        "ref_mood": ref_mood,
        "ref_colors": ref_colors,
        "scenes": scenes_ctx,
        "camera": camera,
        "lens": lens,
        "format": video_format,
        "num_scenes": num_scenes,
    }, ensure_ascii=False)

    prompt = (
        "Tu es un directeur artistique pour du contenu video court (reels, shorts).\n"
        "Analyse ce brief et sa metadata de reference pour decider de la direction artistique du montage.\n\n"
        "REGLES :\n"
        "1. COHERENCE MOOD-TRANSITION : mood intense -> transitions rapides (cut, wipe). "
        "mood contemplatif -> transitions lentes (crossfade, dip-to-black).\n"
        "2. VARIETE : ne jamais utiliser la meme transition 5x de suite. "
        "Utilise sceneOverrides si necessaire.\n"
        "3. PACING DYNAMIQUE : les durees de plans varient. Plan large = plus long. "
        "Closeup = court. Climax = plans courts rapides.\n"
        "4. COLOR GRADE UNIQUE : un seul grade pour tout le film, base sur le mood dominant.\n"
        "5. FONT-MOOD : serif -> elegant/cinema. sans-serif -> moderne/tech. cursive -> emotionnel.\n"
        "6. ACCENT COLOR : extraite de ref_colors (couleur dominante de la palette).\n"
        "7. GRAIN : vintage/film -> 0.1-0.2. modern/clean -> 0.\n"
        "8. AUDIO : musicVolume 0.3-0.6, voiceoverVolume 0.8-1.0, duckLevel 0.1-0.3.\n\n"
        f"Contexte :\n{context_json}\n\n"
        "Retourne UNIQUEMENT un JSON valide conforme a ce schema :\n"
        '{"pacing": "slow|medium|fast|dynamic", '
        '"defaultTransition": "cut|crossfade|dip-to-black|wipe|slide", '
        '"defaultTransitionDurationFrames": 10-45, '
        '"sceneOverrides": {"0": {"transition": "...", "transitionDurationFrames": ...}}, '
        '"colorGrade": {"preset": "none|warm|cold|teal-orange|vintage|bleach-bypass", '
        '"contrast": 0.8-1.3, "saturation": 0.5-1.5, "brightness": 0.8-1.2}, '
        '"grain": 0-0.3, '
        '"typography": {"fontFamily": "...", "accentColor": "#hex", "textColor": "#hex"}, '
        '"subtitleStyle": "reel|cinema|minimal|bold-center|karaoke"}'
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/chat/completions",
                json={
                    "model": "fast",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 1500,
                },
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (429, 400):
                    content = await _call_gemini_direct(prompt, max_tokens=1500)
                    if not content:
                        return dict(_DEFAULT_DIRECTION)
                elif resp.status != 200:
                    print(f"[direction] LLM failed: {resp.status}", flush=True)
                    return dict(_DEFAULT_DIRECTION)
                else:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]

                # Extract JSON
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                direction = json.loads(content.strip())

                # Validate required keys
                required = {"pacing", "defaultTransition", "colorGrade", "typography", "subtitleStyle"}
                if not required.issubset(direction.keys()):
                    missing = required - set(direction.keys())
                    print(f"[direction] Missing keys: {missing}, using defaults", flush=True)
                    merged = dict(_DEFAULT_DIRECTION)
                    merged.update(direction)
                    return merged

                # Ensure defaultTransitionDurationFrames exists
                if "defaultTransitionDurationFrames" not in direction:
                    direction["defaultTransitionDurationFrames"] = 15

                print(f"[direction] LLM direction: transition={direction['defaultTransition']} "
                      f"grade={direction['colorGrade'].get('preset', '?')} "
                      f"pacing={direction['pacing']}", flush=True)
                return direction
    except Exception as exc:
        print(f"[direction] Error: {exc}", flush=True)
        return dict(_DEFAULT_DIRECTION)


async def _step_research(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle research step: analyze URL or search Qdrant.

    If a video URL is provided, downloads from MeTube if needed, then runs
    full analysis pipeline (ffmpeg scene detect → keyframes → Claude Vision).
    If no URL, searches Qdrant for similar references, then uses LLM to
    decompose the brief into multiple structured scenes.
    """
    url = params.get("url", job.get("url", ""))
    extras: dict[str, Any] = {}
    research_result: dict[str, Any] = {}
    num_scenes = int(params.get("num_scenes", 5))

    if url:
        # Try to download from MeTube if not already in watch dir
        filename = Path(url).name if "/" in url else url
        from urllib.parse import unquote
        filename = unquote(filename)
        src = WATCH_DIR / filename

        if not src.exists() and ("tube." in url or "download" in url):
            downloaded = await _download_metube_video(url, WATCH_DIR)
            if downloaded:
                src = downloaded
                filename = downloaded.name

        if src.exists():
            research_result = await run_analysis(filename)
            extras["scene_analyses"] = research_result.get("scenes", [])
        else:
            research_result = {"note": f"File not in watch dir: {filename}"}
            print(f"[research] Video not found locally, falling back to LLM decomposition", flush=True)
    else:
        # Search Qdrant for similar references
        query = params.get("query", job.get("title", ""))
        results = await _search_qdrant(query, limit=5)
        research_result = {"qdrant_results": results}

        # Extract style/mood/colors from Qdrant results to use as reference
        # This ensures storyboard respects the reference even without video file
        # Pick FIRST result that has style/mood/prompt (skip transcripts)
        if results and isinstance(results, list):
            payload = {}
            for candidate in results:
                p = candidate.get("payload", candidate) if isinstance(candidate, dict) else {}
                has_style = bool(p.get("style"))
                has_mood = bool(p.get("mood"))
                has_prompt = bool(p.get("suggested_prompt"))
                print(f"[research] candidate keys={list(p.keys())[:5]} style={has_style} mood={has_mood} prompt={has_prompt}", flush=True)
                if has_style or has_mood or has_prompt:
                    payload = p
                    break
            # Fallback to first result if none had style
            if not payload:
                payload = results[0].get("payload", results[0]) if isinstance(results[0], dict) else {}

            qdrant_style = payload.get("style", "")
            qdrant_mood = payload.get("mood", "")
            qdrant_colors = payload.get("colors", "")
            qdrant_prompt = payload.get("suggested_prompt", "")

            if qdrant_style or qdrant_mood or qdrant_prompt:
                extras["ref_style"] = qdrant_style
                extras["ref_mood"] = qdrant_mood
                extras["ref_colors"] = qdrant_colors

                # Decompose brief into multiple scenes via LLM
                # (instead of 1 synthetic scene)
                llm_scenes = await _llm_decompose_scenes(
                    description=job.get("description", job.get("title", "")),
                    num_scenes=num_scenes,
                    style=qdrant_style,
                    mood=qdrant_mood,
                    colors=qdrant_colors,
                )
                if llm_scenes:
                    extras["scene_analyses"] = llm_scenes
                    print(f"[research] LLM decomposed into {len(llm_scenes)} scenes (Qdrant ref: {qdrant_style})", flush=True)
                else:
                    # Fallback: single synthetic scene
                    extras["scene_analyses"] = [{
                        "scene_index": 0,
                        "analysis": {
                            "style": qdrant_style or "cinematic",
                            "mood": qdrant_mood or "dramatic",
                            "colors": qdrant_colors,
                            "suggested_prompt": qdrant_prompt,
                        },
                    }]
                    print(f"[research] Fallback single scene: style={qdrant_style}", flush=True)

    # Final safety: if scene_analyses is still empty, decompose via LLM
    if not extras.get("scene_analyses"):
        print("[research] No scenes from analysis or Qdrant, decomposing via LLM", flush=True)
        llm_scenes = await _llm_decompose_scenes(
            description=job.get("description", job.get("title", "")),
            num_scenes=num_scenes,
        )
        if llm_scenes:
            extras["scene_analyses"] = llm_scenes

    kitsu_result = await _kitsu_step_task(
        job, "Recherche", "done",
        f"Research completed. {len(extras.get('scene_analyses', []))} scenes.\n{json.dumps(research_result, indent=2)[:1500]}",
    )

    # Generate mood board from REAL analysis (style, colors, mood from video ref)
    mood_preview_id = ""
    mood_bytes: bytes | None = None
    concept_id = job.get("concept_id", extras.get("concept_id", ""))
    project_id = job.get("kitsu_project_id", "")
    scenes = extras.get("scene_analyses", research_result.get("scenes", []))

    if scenes:
        try:
            # Build mood prompt from REAL video analysis
            first_scene = scenes[0] if scenes else {}
            analysis = first_scene.get("analysis", first_scene)
            ref_style = analysis.get("style", "cinematic")
            ref_mood = analysis.get("mood", "dramatic")
            ref_colors = analysis.get("colors", "")
            ref_prompt = analysis.get("suggested_prompt", "")
            description = job.get("description", job.get("title", ""))

            mood_prompt = (
                f"professional cinematic mood board, visual reference sheet: "
                f"{description[:150]}. "
                f"Style: {ref_style}. Mood: {ref_mood}. "
                f"Color palette: {ref_colors}. "
                f"Based on reference: {ref_prompt[:100]}. "
                f"concept art, multiple panels, color swatches"
            )

            mood_model = await _composer_select_model(
                "storyboard text-to-image concept art mood board", "eco",
            )
            if mood_model:
                mood_wf = await _composer_build_workflow(
                    mood_model, mood_prompt,
                    width=1024, height=768,
                    style=ref_style,
                    camera=job.get("camera", ""),
                    lens=job.get("lens", ""),
                )
                mood_result = await _composer_submit(
                    mood_wf, wait=True, timeout_s=120,
                )
                mood_images = mood_result.get("images", [])
                if mood_images:
                    mood_bytes = await _composer_download_image(mood_images[0])
                    if mood_bytes:
                        print(f"[research] Mood board generated: {len(mood_bytes)} bytes", flush=True)
                    if mood_bytes and concept_id and KITSU_URL:
                        async with aiohttp.ClientSession() as ks:
                            mood_preview_id = await _kitsu_upload_concept_preview(
                                ks, concept_id, mood_bytes,
                            ) or ""
                        if mood_preview_id and not mood_preview_id.startswith("error"):
                            print(f"[research] Concept preview uploaded: {mood_preview_id[:12]}", flush=True)
                        else:
                            # Retry once
                            print(f"[research] Concept preview upload failed, retrying...", flush=True)
                            async with aiohttp.ClientSession() as ks2:
                                mood_preview_id = await _kitsu_upload_concept_preview(
                                    ks2, concept_id, mood_bytes,
                                ) or ""
                            if mood_preview_id:
                                print(f"[research] Concept preview retry OK: {mood_preview_id[:12]}", flush=True)
                            else:
                                print("[research] ERROR: Concept preview upload failed after retry", flush=True)
        except Exception as mood_exc:
            print(f"[research] Mood board error: {mood_exc}", flush=True)
            mood_preview_id = f"error: {mood_exc}"

    kitsu_result["mood_preview_id"] = mood_preview_id

    # Send Telegram notification with mood board preview
    await _notify_step_completed(job, "research", preview_bytes=mood_bytes)

    return {
        "status": "ok",
        "research": research_result,
        "kitsu": kitsu_result,
    }, extras


async def _step_script(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle script step: generate prompts per scene with camera presets."""
    scenes = params.get("scenes", job.get("scene_analyses", job.get("scenes", [])))
    modifications_raw = params.get("modifications", {})
    # Parse string modifications: "key=val,key2=val2" → dict
    if isinstance(modifications_raw, str):
        modifications = {}
        for part in modifications_raw.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                modifications[k.strip()] = v.strip()
    else:
        modifications = modifications_raw or {}
    presets = await _load_camera_presets()

    # --- Priority 1: Pre-computed scene_prompts from OpenClaw Director ---
    pre_prompts = params.get("scene_prompts")
    if pre_prompts:
        if isinstance(pre_prompts, str):
            pre_prompts = json.loads(pre_prompts)
        print(f"[script] Using {len(pre_prompts)} pre-computed scene_prompts from Director", flush=True)
        # Inject camera tokens and store directly
        scene_prompts: list[dict[str, Any]] = []
        for idx, sp in enumerate(pre_prompts):
            prompt = sp.get("visual_prompt", sp.get("enriched", sp.get("description", "")))
            enriched = _inject_camera_tokens(
                prompt,
                camera=job.get("camera", ""),
                lens=job.get("lens", ""),
                aperture=job.get("aperture", ""),
                motion=job.get("motion", ""),
            )
            scene_prompts.append({
                "scene_index": sp.get("scene_index", idx),
                "original": prompt,
                "enriched": enriched,
                "duration_seconds": sp.get("duration_seconds", 5),
                "camera_movement": sp.get("camera_movement", "static"),
            })
        extras: dict[str, Any] = {
            "scene_prompts": scene_prompts,
            "scene_prompts_source": "director",
        }
        # Direction is set by the Director or defaults
        direction = params.get("direction", _DEFAULT_DIRECTION)
        extras["direction"] = direction
        kitsu_comment = "\n\n".join(
            f"Scene {p['scene_index']+1}:\n{p['enriched']}" for p in scene_prompts
        )
        kitsu_result = await _kitsu_step_task(
            job, "Script", "done", f"Script (Director):\n\n{kitsu_comment[:3000]}",
        )
        await _notify_step_completed(job, "script")
        return {
            "status": "ok", "source": "director",
            "scene_prompts": scene_prompts, "direction": direction,
            "kitsu": kitsu_result,
        }, extras

    # --- Priority 2/3: Generate scenes (Claude CLI → LiteLLM fallback) ---
    # Detect poor/synthetic scene data → enrich via LLM
    is_poor = (
        len(scenes) <= 1
        or all(s.get("llm_generated") for s in scenes)
        or not any(
            s.get("analysis", s).get("suggested_prompt", "")
            for s in scenes
        )
    )
    if is_poor:
        num_scenes = int(params.get("num_scenes", 5))
        description = job.get("description", job.get("title", ""))
        ref_style = job.get("ref_style", "")
        ref_mood = job.get("ref_mood", "")
        ref_colors = job.get("ref_colors", "")

        # Priority 2: Claude Code CLI (Max OAuth, Opus 4.6)
        llm_scenes = await _claude_cli_decompose_scenes(
            description=description, num_scenes=num_scenes,
            style=ref_style, mood=ref_mood, colors=ref_colors,
        )
        source = "claude-cli"

        # Priority 3: LiteLLM fallback (claude-sonnet, not eco)
        if not llm_scenes:
            print(f"[script] Claude CLI unavailable, falling back to LiteLLM claude-sonnet", flush=True)
            llm_scenes = await _llm_decompose_scenes(
                description=description, num_scenes=num_scenes,
                style=ref_style, mood=ref_mood, colors=ref_colors,
            )
            source = "litellm-sonnet"

        if llm_scenes:
            print(f"[script] Decomposed into {len(llm_scenes)} scenes via {source}", flush=True)
            scenes = llm_scenes

    scene_prompts: list[dict[str, Any]] = []
    for idx, scene in enumerate(scenes):
        base_prompt = scene.get("analysis", {}).get("suggested_prompt", "")
        if not base_prompt:
            base_prompt = scene.get("suggested_prompt", f"Scene {idx + 1}")

        # Apply camera tokens
        enriched = _inject_camera_tokens(
            base_prompt,
            camera=job.get("camera", ""),
            lens=job.get("lens", ""),
            aperture=job.get("aperture", ""),
            motion=job.get("motion", ""),
        )

        # Apply modifications via LiteLLM if available
        if modifications and LITELLM_URL:
            mod_text = "\n".join(f"- {k}: {v}" for k, v in modifications.items())
            remix_text = await _call_litellm_text(
                f"Modify this image prompt:\n{enriched}\n\nChanges:\n{mod_text}\n\nReturn ONLY the modified prompt."
            )
            if remix_text:
                enriched = remix_text

        scene_prompts.append({
            "scene_index": idx,
            "original": base_prompt,
            "enriched": enriched,
            "duration_seconds": scene.get("duration", scene.get("duration_seconds", 5)),
            "camera_movement": scene.get("analysis", scene).get("camera_movement", ""),
        })

    extras: dict[str, Any] = {"scene_prompts": scene_prompts}

    # Post all prompts as Kitsu comment
    comment = "\n\n".join(
        f"Scene {p['scene_index']+1}:\n{p['enriched']}" for p in scene_prompts
    )
    kitsu_result = await _kitsu_step_task(
        job, "Script", "done", f"Script prompts:\n\n{comment[:3000]}",
    )

    # Create Kitsu assets (by entity) + shots (by scene) + breakdown
    project_id = job.get("kitsu_project_id", "")
    sequence_id = job.get("kitsu_sequence_id", "")
    if project_id and sequence_id and KITSU_URL and KITSU_TOKEN:
        try:
            async with aiohttp.ClientSession() as ks:
                # --- Assets by entity (characters, environments, props) ---
                entities = await _llm_extract_entities(
                    job.get("description", job.get("title", "")),
                )
                # Map category → asset_type_id
                char_type_id = await _kitsu_get_asset_type_id(ks, "Characters")
                env_type_id = await _kitsu_get_asset_type_id(ks, "Environment")
                prop_type_id = await _kitsu_get_asset_type_id(ks, "Props")
                category_type_map = {
                    "characters": char_type_id,
                    "environments": env_type_id,
                    "props": prop_type_id,
                }

                asset_ids: list[str] = []
                asset_names: list[str] = []
                for category, names in entities.items():
                    type_id = category_type_map.get(category)
                    if not type_id:
                        continue
                    for name in names:
                        asset = await _kitsu_create_asset(
                            ks, project_id, type_id,
                            name=name,
                            description=f"{category.rstrip('s').title()}: {name}",
                            data={
                                "ai_prompt": f"{name}, {job.get('ref_style', 'cinematic')} style",
                                "style": job.get("ref_style", ""),
                                "mood": job.get("ref_mood", ""),
                            },
                        )
                        if asset and "id" in asset:
                            asset_ids.append(asset["id"])
                            asset_names.append(name)
                            print(f"[script] Asset: {name} ({category})", flush=True)

                # --- Shots by scene (SH0010, SH0020, ...) ---
                shot_ids: list[str] = list(job.get("kitsu_shot_ids", []))
                fps = int(job.get("fps", 24))
                for sp in scene_prompts:
                    idx = sp.get("scene_index", 0)
                    duration = sp.get("duration_seconds", 5)
                    frame_in = idx * duration * fps + 1
                    frame_out = (idx + 1) * duration * fps

                    shot_name = f"SH{(idx + 1) * 10:04d}"
                    shot = await _kitsu_create_shot(
                        ks, project_id, sequence_id, "",
                        shot_name,
                        {
                            "prompt": sp.get("enriched", "")[:300],
                            "scene_index": idx,
                            "duration": duration,
                            "camera_movement": sp.get("camera_movement", ""),
                            "frame_in": frame_in,
                            "frame_out": frame_out,
                        },
                    )
                    if shot and "id" in shot:
                        shot_ids.append(shot["id"])

                        # Cast ALL assets into each shot (simplified)
                        for asset_id in asset_ids:
                            await _kitsu_cast_asset_to_shot(
                                ks, project_id, shot["id"], asset_id,
                            )

                extras["kitsu_shot_ids"] = shot_ids
                extras["kitsu_asset_ids"] = asset_ids
                kitsu_result["assets_created"] = len(asset_ids)
                kitsu_result["asset_names"] = asset_names
                kitsu_result["shots_created"] = len(scene_prompts)
                print(f"[script] Kitsu: {len(asset_ids)} assets, {len(scene_prompts)} shots, breakdown linked", flush=True)
        except Exception as exc:
            kitsu_result["asset_error"] = str(exc)
            print(f"[script] Kitsu error: {exc}", flush=True)

    # Artistic direction for Remotion montage
    direction = await _llm_artistic_direction(
        description=job.get("description", job.get("title", "")),
        title=job.get("title", ""),
        ref_style=job.get("ref_style", ""),
        ref_mood=job.get("ref_mood", ""),
        ref_colors=str(job.get("ref_colors", "")),
        scene_analyses=job.get("scene_analyses", []),
        camera=job.get("camera", ""),
        lens=job.get("lens", ""),
        video_format=job.get("format", "landscape"),
        num_scenes=len(scene_prompts),
    )
    extras["direction"] = direction

    # Send Telegram notification
    await _notify_step_completed(job, "script")

    return {
        "status": "ok",
        "scene_prompts": scene_prompts,
        "direction": direction,
        "kitsu": kitsu_result,
    }, extras


async def _step_storyboard(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle storyboard step: generate low-res frames via Composer.

    Composer selects: NanoBanana2 (eco), FluxSchnell (balanced), or FluxPro (premium).
    Best practice 2026: storyboard = fast + cheap, iterate quickly.
    Auto-skipped when Director provided scene_prompts (no image generation needed).
    """
    # Auto-skip when Director provided scene_prompts (no generation needed)
    if job.get("scene_prompts_source") == "director" and not params.get("force"):
        note = "Skipped — scene_prompts from Director (use --force to override)"
        print(f"[storyboard] {note}", flush=True)
        kitsu_result = await _kitsu_step_task(job, "Storyboard", "done", note)
        return {"status": "ok", "skipped": True, "note": note, "kitsu": kitsu_result}, {}

    scene_prompts = job.get("scene_prompts", [])
    budget = params.get("budget", "eco")  # Storyboard = eco by default
    results: list[dict[str, Any]] = []

    # Select best model for storyboard task
    model = await _composer_select_model("storyboard text-to-image fast cheap", budget)
    model_name = model["name"] if model else "fallback"

    # If no scene_prompts yet, build from description + reference style/mood
    if not scene_prompts:
        desc = job.get("description", job.get("title", ""))
        ref_style = job.get("ref_style", job.get("style", ""))
        ref_mood = job.get("ref_mood", "")
        ref_colors = job.get("ref_colors", "")

        # Enrich with video ref analysis data if available
        if desc:
            enriched = desc
            if ref_style:
                enriched = f"{enriched}, {ref_style} style"
            if ref_mood:
                enriched = f"{enriched}, {ref_mood} mood"
            if ref_colors:
                enriched = f"{enriched}, color palette: {ref_colors}"

            # Also check scene_analyses for richer prompts
            scene_analyses = job.get("scene_analyses", [])
            if scene_analyses:
                for idx, sa in enumerate(scene_analyses):
                    analysis = sa.get("analysis", sa)
                    suggested = analysis.get("suggested_prompt", "")
                    if suggested:
                        scene_prompts.append({
                            "enriched": _inject_camera_tokens(
                                suggested,
                                camera=job.get("camera", ""),
                                lens=job.get("lens", ""),
                            ),
                            "original": suggested,
                            "scene_index": idx,
                        })
            # Fallback: use enriched description as single prompt
            if not scene_prompts:
                scene_prompts = [{"enriched": enriched, "original": desc, "scene_index": 0}]

    for sp in scene_prompts:
        prompt = sp.get("enriched", sp.get("original", ""))
        if not prompt:
            continue

        scene_result: dict[str, Any] = {
            "scene": sp.get("scene_index", 0),
            "model": model_name,
            "prompt": prompt[:100],
        }

        if model:
            # Composer workflow: selected model
            workflow = await _composer_build_workflow(
                model, prompt,
                negative=sp.get("negative", "blurry, low quality"),
                width=768, height=512,  # Low-res for storyboard
                style=job.get("style", ""),
                camera=job.get("camera", ""),
                lens=job.get("lens", ""),
            )
            # Submit and WAIT for completion
            submit_result = await _composer_submit(workflow, wait=True, timeout_s=180)
            scene_result["comfyui"] = submit_result

            # Download generated image if available
            images = submit_result.get("images", [])
            if images:
                img_bytes = await _composer_download_image(images[0])
                if img_bytes:
                    scene_result["image_size"] = len(img_bytes)
                    # Save locally
                    img_path = COMFYUI_DIR / f"storyboard_{job['job_id'][:8]}_s{sp.get('scene_index',0)}.png"
                    img_path.write_bytes(img_bytes)
                    scene_result["image_path"] = str(img_path)

                    # Upload to Kitsu as preview on the scene's shot (or overview)
                    if KITSU_URL and KITSU_TOKEN:
                        try:
                            project_id = job.get("kitsu_project_id", "")
                            scene_idx = sp.get("scene_index", 0)
                            # shot_ids from _step_script = scene shots (no overview)
                            shot_ids = job.get("kitsu_shot_ids", [])
                            if scene_idx < len(shot_ids):
                                shot_id = shot_ids[scene_idx]
                            elif shot_ids:
                                shot_id = shot_ids[-1]
                            else:
                                shot_id = job.get("kitsu_overview_shot_id", "")
                            if shot_id and project_id:
                                async with aiohttp.ClientSession() as ks:
                                    task_type_id = await _kitsu_get_task_type_id(ks, "Storyboard CF")
                                    task = await _kitsu_get_or_create_task(
                                        ks, shot_id, task_type_id, project_id,
                                    )
                                    wfa_id = await _kitsu_get_status_id(ks, "wfa")
                                    comment = await _kitsu_post_comment(
                                        ks, task["id"], wfa_id,
                                        f"Storyboard S{scene_idx} — {model_name}\n{prompt[:200]}",
                                    )
                                    if comment and comment.get("id"):
                                        preview_id = await _kitsu_upload_preview(
                                            ks, task["id"], comment["id"], img_bytes,
                                        )
                                        scene_result["kitsu_preview_id"] = preview_id
                                        scene_result["kitsu_shot_id"] = shot_id
                        except Exception as ke:
                            scene_result["kitsu_error"] = str(ke)
        else:
            # Fallback to n8n creative pipeline
            n8n_result = await _call_n8n_creative(
                prompt=prompt, output_type="image",
                resolution="low-res",
                scene_index=sp.get("scene_index", 0),
                job_id=job["job_id"],
            )
            scene_result["n8n"] = n8n_result

        results.append(scene_result)

    kitsu_result = await _kitsu_step_task(
        job, "Storyboard CF", "wfa",
        f"Storyboard: {len(results)} frames via {model_name}. Awaiting validation.",
    )

    # Send Telegram notification with first storyboard frame as preview
    # Keep the image bytes from generation (more reliable than re-reading from disk)
    first_frame_bytes: bytes | None = None
    for r in results:
        # img_bytes was saved during generation — use it directly if available
        path_str = r.get("image_path", "")
        if path_str:
            try:
                first_frame_bytes = Path(path_str).read_bytes()
                print(f"[storyboard] Read {len(first_frame_bytes)} bytes from {path_str}", flush=True)
            except Exception as read_exc:
                print(f"[storyboard] Failed to read {path_str}: {read_exc}", flush=True)
            break
    tg_ok = await _notify_step_completed(job, "storyboard", preview_bytes=first_frame_bytes)
    print(f"[storyboard] Telegram notify: ok={tg_ok} has_preview={first_frame_bytes is not None}", flush=True)

    return {
        "status": "ok",
        "model_used": model_name,
        "budget": budget,
        "frames_generated": len([r for r in results if r.get("image_path")]),
        "storyboard_results": results,
        "kitsu": kitsu_result,
    }, {}


async def _step_voiceover(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle voiceover step: Kokoro (preview) or Chatterbox (prod via CCX33)."""
    skip = params.get("skip", False)
    if skip:
        kitsu_result = await _kitsu_step_task(job, "Voice-over", "done", "Skipped by user")
        return {"status": "ok", "note": "Skipped", "kitsu": kitsu_result}, {}

    text = params.get("text", "")
    voice_ref = params.get("voice_ref")
    mode = params.get("mode", "preview")  # preview (Kokoro local) or prod (Chatterbox CCX33)

    if not text:
        kitsu_result = await _kitsu_step_task(
            job, "Voice-over", "done", "No text provided — manual voiceover",
        )
        return {"status": "ok", "note": "No text — manual step", "kitsu": kitsu_result}, {}

    result: dict[str, Any] = {}
    if mode == "prod" and os.environ.get("RENDER_SERVER_URL"):
        # Production: Chatterbox on ephemeral CCX33
        try:
            async with aiohttp.ClientSession() as session:
                body: dict[str, Any] = {"text": text, "output_name": f"{job['job_id'][:8]}-vo"}
                if voice_ref:
                    body["voice_ref"] = voice_ref
                async with session.post(
                    f"{os.environ['RENDER_SERVER_URL']}/tts",
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    result = await resp.json()
        except Exception as exc:
            result = {"error": f"Chatterbox CCX33: {exc}"}
    else:
        # Preview: Kokoro local (fast, 82M params)
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _kokoro_generate, text, job["job_id"])
        except Exception as exc:
            result = {"error": f"Kokoro local: {exc}"}

    note = f"Voice-over ({mode}): {result.get('output_path', result.get('error', '?'))}"
    kitsu_result = await _kitsu_step_task(job, "Voice-over", "done", note)
    await _notify_step_completed(job, "voiceover")
    return {"status": "ok", "mode": mode, "result": result, "kitsu": kitsu_result}, {}


def _kokoro_generate(text: str, job_id: str) -> dict[str, Any]:
    """Generate TTS with Kokoro (synchronous, runs in executor)."""
    try:
        from kokoro import KPipeline
        import soundfile as sf

        pipeline = KPipeline(lang_code="a")  # 'a' = auto-detect
        audio_chunks = []
        for _, _, audio in pipeline(text):
            audio_chunks.append(audio)

        if not audio_chunks:
            return {"error": "No audio generated"}

        import numpy as np
        full_audio = np.concatenate(audio_chunks)
        out_path = OUTPUT_DIR / f"{job_id[:8]}-kokoro-vo.wav"
        sf.write(str(out_path), full_audio, 24000)
        return {"output_path": str(out_path), "duration_s": len(full_audio) / 24000}
    except ImportError:
        return {"error": "Kokoro not installed in container"}
    except Exception as exc:
        return {"error": str(exc)}


async def _step_music(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle music step: ACE-Step on ephemeral CCX33."""
    skip = params.get("skip", False)
    if skip:
        kitsu_result = await _kitsu_step_task(job, "Music", "done", "Skipped by user")
        return {"status": "ok", "note": "Skipped", "kitsu": kitsu_result}, {}

    mood = params.get("mood", job.get("description", "cinematic"))
    duration = params.get("duration", 60)
    render_url = os.environ.get("RENDER_SERVER_URL", "")

    if not render_url:
        note = "No render server configured. Provide RENDER_SERVER_URL (CCX33 ephemeral)."
        kitsu_result = await _kitsu_step_task(job, "Music", "done", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{render_url}/music",
                json={
                    "prompt": f"{mood}, cinematic background music, instrumental",
                    "duration": duration,
                    "output_name": f"{job['job_id'][:8]}-music",
                },
                timeout=aiohttp.ClientTimeout(total=600),
            ) as resp:
                result = await resp.json()

        note = f"Music generated: {result.get('output_path', result.get('error', '?'))}"
        kitsu_result = await _kitsu_step_task(job, "Music", "wfa", note)
        return {"status": "ok", "result": result, "kitsu": kitsu_result}, {}
    except Exception as exc:
        note = f"Music generation failed: {exc}"
        kitsu_result = await _kitsu_step_task(job, "Music", "done", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}


async def _step_imagegen(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle imagegen step: generate hi-res keyframes via Composer.

    Best practice 2026: generate at model-native res, then upscale.
    Composer selects: FluxPro1.1 (premium), NanoBananaPro (balanced), HiDream (eco).
    Auto-skipped when Director provided scene_prompts (videogen uses txt2vid directly).
    """
    # Auto-skip when Director provided scene_prompts (no keyframe generation needed)
    if job.get("scene_prompts_source") == "director" and not params.get("force"):
        note = "Skipped — scene_prompts from Director, videogen will use txt2vid (use --force to override)"
        print(f"[imagegen] {note}", flush=True)
        kitsu_result = await _kitsu_step_task(job, "Image Gen", "done", note)
        return {"status": "ok", "skipped": True, "note": note, "kitsu": kitsu_result}, {}

    scene_prompts = job.get("scene_prompts", [])
    budget = params.get("budget", "balanced")
    job_prefix = job["job_id"][:8]
    results: list[dict[str, Any]] = []

    # Parse target resolution from Kitsu project
    resolution = job.get("resolution", "1920x1080")
    try:
        target_w, target_h = [int(x) for x in resolution.split("x")]
    except (ValueError, AttributeError):
        target_w, target_h = 1920, 1080

    # Select best model for keyframe generation
    model = await _composer_select_model("keyframe final render high quality image", budget)
    model_name = model["name"] if model else "fallback"
    print(f"[imagegen] Selected model: {model_name} node={model.get('node', '?') if model else '?'}", flush=True)

    # Generate at model-optimal resolution (not target — upscale later)
    gen_w = min(target_w, 1344) if target_w > target_h else min(target_w, 768)
    gen_h = min(target_h, 768) if target_w > target_h else min(target_h, 1344)
    # Ensure multiple of 8
    gen_w = (gen_w // 8) * 8
    gen_h = (gen_h // 8) * 8

    dry_run = params.get("dry_run", False)

    for sp in scene_prompts:
        prompt = sp.get("enriched", sp.get("original", ""))
        if not prompt:
            continue

        if model:
            workflow = await _composer_build_workflow(
                model, prompt,
                negative=sp.get("negative", "blurry, low quality, deformed"),
                width=gen_w, height=gen_h,
                style=job.get("style", ""),
                camera=job.get("camera", ""),
                lens=job.get("lens", ""),
            )

            if dry_run:
                submit_result = await _composer_submit(workflow, dry_run=True)
                scene_idx = sp.get("scene_index", 0)
                sp["keyframe_path"] = f"/dry-run/placeholder_s{scene_idx}.png"
                results.append({
                    "scene": scene_idx, "model": model_name,
                    "gen_resolution": f"{gen_w}x{gen_h}",
                    "target_resolution": resolution,
                    "dry_run": True, "comfyui_valid": submit_result.get("valid", False),
                    "result": submit_result,
                })
                continue

            submit_result = await _composer_submit(workflow)

            # Download keyframe and link to scene_prompt for img2vid
            scene_idx = sp.get("scene_index", 0)
            if submit_result.get("status") == "completed":
                images = submit_result.get("images", [])
                if images:
                    try:
                        img_bytes = await _composer_download_image(images[0])
                        if img_bytes:
                            kf_path = OUTPUT_DIR / f"{job_prefix}_keyframe_s{scene_idx}.png"
                            kf_path.write_bytes(img_bytes)
                            # CRITICAL WIRING: link keyframe to scene_prompt for videogen
                            sp["keyframe_path"] = str(kf_path)
                            print(f"[imagegen] Keyframe s{scene_idx} saved: {kf_path.name}", flush=True)
                            # Upload to Kitsu asset as style reference
                            asset_ids = job.get("kitsu_asset_ids", [])
                            if asset_ids and KITSU_URL and KITSU_TOKEN:
                                try:
                                    async with aiohttp.ClientSession() as ks:
                                        # First keyframe → first asset (style anchor)
                                        target_id = asset_ids[min(scene_idx, len(asset_ids) - 1)]
                                        preview_id = await _kitsu_upload_asset_preview(
                                            ks, target_id, img_bytes,
                                            note=f"Keyframe s{scene_idx} — style reference",
                                        )
                                        if preview_id:
                                            print(f"[imagegen] Uploaded keyframe s{scene_idx} to Kitsu asset", flush=True)
                                except Exception as kitsu_exc:
                                    print(f"[imagegen] Kitsu upload error: {kitsu_exc}", flush=True)
                    except Exception as dl_exc:
                        print(f"[imagegen] Keyframe download error s{scene_idx}: {dl_exc}", flush=True)

            # Generate short asset name for Kitsu
            analysis = sp.get("analysis", {})
            asset_name = _generate_asset_name(analysis, job.get("title", ""))

            results.append({
                "scene": scene_idx,
                "model": model_name,
                "asset_name": asset_name,
                "gen_resolution": f"{gen_w}x{gen_h}",
                "target_resolution": resolution,
                "needs_upscale": gen_w < target_w or gen_h < target_h,
                "keyframe_path": sp.get("keyframe_path", ""),
                "result": submit_result,
            })
        else:
            n8n_result = await _call_n8n_creative(
                prompt=prompt, output_type="image", resolution="hi-res",
                scene_index=sp.get("scene_index", 0), job_id=job["job_id"],
            )
            results.append({"scene": sp.get("scene_index", 0), "model": "n8n", "result": n8n_result})

    needs_upscale = any(r.get("needs_upscale") for r in results)
    kitsu_note = (
        f"Keyframes: {len(results)} images via {model_name} "
        f"at {gen_w}x{gen_h}"
        f"{' (upscale needed → ' + resolution + ')' if needs_upscale else ''}. "
        f"Validate before video generation."
    )
    total_cost = len(results) * (model.get("cost", 0) if model else 0)
    kitsu_result = await _kitsu_step_task(
        job, "Image Gen", "wfa", kitsu_note, cost_usd=total_cost,
    )

    # Send Telegram notification
    await _notify_step_completed(job, "imagegen")

    return {
        "status": "ok",
        "model_used": model_name,
        "budget": budget,
        "gen_resolution": f"{gen_w}x{gen_h}",
        "target_resolution": resolution,
        "needs_upscale": needs_upscale,
        "estimated_cost_usd": total_cost,
        "imagegen_results": results,
        "kitsu": kitsu_result,
    }, {}


async def _step_videogen(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle videogen step: generate video clips via Composer.

    Best practice 2026: Kling 3.0 = best value, Seedance = best creative control.
    Budget eco → Seedance 2.0 ($0.10), balanced → Kling 2.6 ($0.15), premium → Veo 3.1.
    Prefer img2vid (keyframe → clip) over txt2vid for consistency.
    """
    scene_prompts = job.get("scene_prompts", [])
    budget = params.get("budget", "balanced")
    duration = int(params.get("duration", 5))
    dry_run = params.get("dry_run", False)
    job_prefix = job["job_id"][:8]
    results: list[dict[str, Any]] = []

    # Failsafe: if scene_prompts empty, build from description
    if not scene_prompts:
        print("[videogen] WARNING: scene_prompts empty, building from description", flush=True)
        desc = job.get("description", job.get("title", ""))
        if desc:
            scene_prompts = [{
                "scene_index": 0,
                "original": desc,
                "enriched": _inject_camera_tokens(
                    desc, job.get("camera", ""), job.get("lens", ""),
                ),
                "duration_seconds": duration,
            }]

    # Parse resolution
    resolution = job.get("resolution", "1920x1080")
    try:
        target_w, target_h = [int(x) for x in resolution.split("x")]
    except (ValueError, AttributeError):
        target_w, target_h = 1920, 1080

    # Select best video model — prefer txt2vid unless reference keyframes exist
    has_keyframes = any(
        sp.get("keyframe_path") or sp.get("image_path")
        for sp in scene_prompts
    )
    if has_keyframes:
        vid_query = "video generation img2vid keyframe to clip best value"
    else:
        vid_query = "video generation txt2vid text to video seedance kling best value"
    model = await _composer_select_model(vid_query, budget)
    # Blacklist models with broken fal.ai queue (MiniMax result URL fails)
    _BLACKLISTED_NODES = {"MiniMaxTextToVideo_fal", "MiniMaxSubjectReference_fal"}
    if model and model.get("node") in _BLACKLISTED_NODES:
        print(f"[videogen] Blacklisted {model['node']}, falling back to Seedance", flush=True)
        model = await _composer_select_model("seedance txt2vid text to video", budget)
    model_name = model["name"] if model else "fallback"
    model_node = model.get("node", "") if model else ""
    is_in_specs = model_node in _FAL_NODE_SPECS
    is_in_endpoints = model_node in _FAL_ENDPOINTS
    print(f"[videogen] Selected: {model_name} node={model_node} in_specs={is_in_specs} in_endpoints={is_in_endpoints} query={vid_query}", flush=True)

    # --- Style prefix for visual consistency across scenes ---
    direction = job.get("direction", {})
    style_parts: list[str] = []
    if job.get("ref_style"):
        style_parts.append(job["ref_style"])
    if job.get("ref_colors"):
        style_parts.append(f"color palette: {job['ref_colors']}")
    if job.get("ref_mood"):
        style_parts.append(f"{job['ref_mood']} mood")
    grade_preset = direction.get("colorGrade", {}).get("preset", "")
    if grade_preset and grade_preset != "none":
        style_parts.append(f"{grade_preset} color grading")
    if job.get("camera"):
        style_parts.append(f"shot on {job['camera']}")
    style_prefix = ", ".join(style_parts)
    if style_prefix:
        print(f"[videogen] Style prefix: {style_prefix}", flush=True)

    for sp in scene_prompts:
        prompt = sp.get("enriched", sp.get("original", ""))
        if not prompt:
            continue

        # Inject style prefix for consistency
        if style_prefix:
            prompt = f"{style_prefix}. {prompt}"

        # --- Reference image for img2vid (local path → ComfyUI LoadImage) ---
        ref_image = ""
        kf_path = sp.get("keyframe_path", "")
        if not kf_path:
            # Fallback: look for storyboard frame
            sb_path = COMFYUI_DIR / f"storyboard_{job_prefix}_s{sp.get('scene_index', 0)}.png"
            if sb_path.exists():
                kf_path = str(sb_path)
        if kf_path and Path(kf_path).exists():
            # Pass local path — _composer_build_workflow copies to ComfyUI input dir
            ref_image = kf_path
            print(f"[videogen] Using img2vid ref for scene {sp.get('scene_index')}: {Path(kf_path).name}", flush=True)

        # Fallback: download style anchor from Kitsu asset library
        if not ref_image and job.get("kitsu_asset_ids") and KITSU_URL and KITSU_TOKEN:
            try:
                async with aiohttp.ClientSession() as ks:
                    anchor_id = job["kitsu_asset_ids"][0]
                    preview_bytes = await _kitsu_download_asset_preview(ks, anchor_id)
                    if preview_bytes:
                        anchor_path = OUTPUT_DIR / f"{job_prefix}_style_anchor.png"
                        anchor_path.write_bytes(preview_bytes)
                        ref_image = str(anchor_path)
                        print(f"[videogen] Style anchor from Kitsu asset {anchor_id}", flush=True)
            except Exception as kitsu_exc:
                print(f"[videogen] Kitsu style anchor error: {kitsu_exc}", flush=True)

        if model:
            workflow = await _composer_build_workflow(
                model, prompt,
                width=target_w, height=target_h,
                reference_image=ref_image,
                style=job.get("style", ""),
                camera=job.get("camera", ""),
                lens=job.get("lens", ""),
                fps=int(job.get("fps", 24)),
                duration=duration,
            )

            if dry_run:
                # Validate ComfyUI workflow graph without generating
                validate_result = await _composer_submit(workflow, dry_run=True)
                mock_fal = _fal_submit_mock(sp.get("scene_index", 0))
                results.append({
                    "scene": sp.get("scene_index", 0),
                    "model": model_name,
                    "duration": duration,
                    "dry_run": True,
                    "comfyui_valid": validate_result.get("valid", False),
                    "result": mock_fal,
                })
                continue

            submit_result = await _composer_submit(workflow, timeout_s=600)
            scene_result: dict[str, Any] = {
                "scene": sp.get("scene_index", 0),
                "model": model_name,
                "duration": duration,
                "result": submit_result,
            }

            # Download video from URL if available (video nodes return URLs)
            video_urls = submit_result.get("video_urls", [])
            if video_urls:
                video_bytes = await _composer_download_video(video_urls[0])
                if video_bytes:
                    video_path = OUTPUT_DIR / f"{job['job_id'][:8]}_s{sp.get('scene_index',0)}.mp4"
                    video_path.write_bytes(video_bytes)
                    scene_result["video_path"] = str(video_path)
                    scene_result["video_size"] = len(video_bytes)
                    scene_result["video_url"] = video_urls[0]
                    print(f"[videogen] Downloaded {len(video_bytes)} bytes → {video_path}", flush=True)

                    # Upload video preview to Kitsu shot task
                    shot_ids = job.get("kitsu_shot_ids", [])
                    scene_idx = sp.get("scene_index", 0)
                    project_id = job.get("kitsu_project_id", "")
                    if scene_idx < len(shot_ids) and project_id and KITSU_URL:
                        try:
                            async with aiohttp.ClientSession() as ks:
                                vg_type_id = await _kitsu_get_task_type_id(ks, "Video Gen")
                                vg_task = await _kitsu_get_or_create_task(
                                    ks, shot_ids[scene_idx], vg_type_id, project_id,
                                )
                                if vg_task:
                                    wfa_id = await _kitsu_get_status_id(ks, "wfa")
                                    vg_comment = await _kitsu_post_comment(
                                        ks, vg_task["id"], wfa_id,
                                        f"Video S{scene_idx} — {model_name}, {duration}s",
                                    )
                                    if vg_comment and vg_comment.get("id"):
                                        await _kitsu_upload_preview(
                                            ks, vg_task["id"], vg_comment["id"], video_bytes,
                                        )
                                        print(f"[videogen] Kitsu preview uploaded for shot {scene_idx}", flush=True)
                        except Exception as ke:
                            print(f"[videogen] Kitsu video preview error: {ke}", flush=True)

            results.append(scene_result)
        else:
            n8n_result = await _call_n8n_video(
                prompt=prompt,
                scene_index=sp.get("scene_index", 0),
                job_id=job["job_id"],
            )
            results.append({"scene": sp.get("scene_index", 0), "model": "n8n", "result": n8n_result})

    total_cost = sum(
        (model.get("cost", 0) if model else 0) for _ in results
    )
    video_count = len([r for r in results if r.get("video_path")])
    kitsu_note = (
        f"Video: {len(results)} clips via {model_name}, "
        f"{duration}s each, {video_count} downloaded, ~${total_cost:.2f} total. "
        f"Awaiting validation."
    )
    kitsu_result = await _kitsu_step_task(
        job, "Video Gen", "wfa", kitsu_note, cost_usd=total_cost,
    )

    # Send Telegram notification with video URL (streaming link)
    first_video_url = ""
    for r in results:
        vu = r.get("video_url", "")
        if vu and vu.startswith("http"):
            first_video_url = vu
            break
    if first_video_url:
        # Send video URL as streaming link via sendVideo (Telegram fetches it)
        await _send_telegram_video_url(first_video_url, job, "videogen")
    else:
        await _notify_step_completed(job, "videogen")

    return {
        "status": "ok",
        "model_used": model_name,
        "budget": budget,
        "duration_per_clip": duration,
        "estimated_cost_usd": total_cost,
        "videogen_results": results,
        "kitsu": kitsu_result,
    }, {}


def _parse_srt(srt_text: str) -> list[dict[str, Any]]:
    """Parse SRT string into list of {text, startMs, endMs}."""
    import re
    lines: list[dict[str, Any]] = []
    blocks = re.split(r"\n\n+", srt_text.strip())
    for block in blocks:
        parts = block.strip().split("\n")
        if len(parts) < 3:
            continue
        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            parts[1],
        )
        if not time_match:
            continue
        g = [int(x) for x in time_match.groups()]
        start_ms = g[0] * 3600000 + g[1] * 60000 + g[2] * 1000 + g[3]
        end_ms = g[4] * 3600000 + g[5] * 60000 + g[6] * 1000 + g[7]
        text = " ".join(parts[2:]).strip()
        if text:
            lines.append({"text": text, "startMs": start_ms, "endMs": end_ms})
    return lines


def _camera_movement_to_ken_burns(movement: str) -> dict[str, Any]:
    """Convert camera_movement string to Ken Burns params."""
    m = movement.lower() if movement else ""
    if "pan left" in m:
        return {"startScale": 1.05, "endScale": 1.05, "panX": -0.8, "panY": 0}
    if "pan right" in m:
        return {"startScale": 1.05, "endScale": 1.05, "panX": 0.8, "panY": 0}
    if "dolly in" in m or "push" in m or "zoom in" in m:
        return {"startScale": 1.0, "endScale": 1.3, "panX": 0, "panY": 0}
    if "dolly out" in m or "pull" in m or "zoom out" in m:
        return {"startScale": 1.3, "endScale": 1.0, "panX": 0, "panY": 0}
    if "crane up" in m or "tilt up" in m:
        return {"startScale": 1.05, "endScale": 1.05, "panX": 0, "panY": -0.5}
    if "crane down" in m or "tilt down" in m:
        return {"startScale": 1.05, "endScale": 1.05, "panX": 0, "panY": 0.5}
    if "tracking" in m:
        return {"startScale": 1.0, "endScale": 1.1, "panX": 0.5, "panY": 0}
    # Default: subtle zoom in
    return {"startScale": 1.0, "endScale": 1.1, "panX": 0, "panY": 0}


async def _montage_ffmpeg_fallback(
    job_prefix: str, video_files: list[Path],
) -> Path | None:
    """Fallback: ffmpeg concat when Remotion is unavailable."""
    concat_path = OUTPUT_DIR / f"{job_prefix}_concat.txt"
    concat_lines = [f"file '{vf}'" for vf in video_files]
    concat_path.write_text("\n".join(concat_lines))
    output_path = OUTPUT_DIR / f"{job_prefix}_final.mp4"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_path), "-c", "copy", str(output_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode != 0:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_path),
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                "-movflags", "+faststart", str(output_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=300)
    except (asyncio.TimeoutError, OSError):
        return None
    return output_path if output_path.exists() else None


async def _step_montage(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle montage step: render final video via Remotion (or ffmpeg fallback).

    Remotion renders the full timeline: title card, scenes with transitions,
    subtitles, audio mix, color grade, grain, outro.
    Artistic direction comes from _step_script() via job["direction"].
    """
    import shutil
    job_prefix = job["job_id"][:8]
    fps = int(job.get("fps", 24))
    dry_run = params.get("dry_run", False)
    extras: dict[str, Any] = {}
    note = ""

    # --- Dry-run: skip ffmpeg normalization + Remotion render ---
    if dry_run:
        scene_prompts = job.get("scene_prompts", [])
        scene_count = len(scene_prompts) if scene_prompts else 0
        total_duration = sum(
            sp.get("duration_seconds", 5) for sp in scene_prompts
        ) if scene_prompts else 0
        direction = job.get("direction", {})
        note = (
            f"DRY-RUN montage: {scene_count} scenes, "
            f"~{total_duration}s total, "
            f"transition={direction.get('defaultTransition', 'crossfade')}, "
            f"grade={direction.get('colorGrade', {}).get('preset', 'none')}. "
            f"Remotion + ffmpeg skipped."
        )
        print(f"[montage] {note}", flush=True)
        kitsu_result = await _kitsu_step_task(job, "Montage", "wfa", note)
        await _notify_step_completed(job, "montage")
        return {
            "status": "ok", "dry_run": True, "note": note,
            "scene_count": scene_count,
            "total_duration_sec": total_duration,
            "render_target": f"720p@{fps}fps",
            "direction": direction,
            "scene_prompts_summary": [
                {"scene": sp.get("scene_index", i), "prompt": sp.get("enriched", sp.get("original", ""))[:120]}
                for i, sp in enumerate(scene_prompts)
            ],
            "render_method": "dry-run",
            "kitsu": kitsu_result,
        }, extras

    # --- Phase 1: Collect assets ---
    video_files: list[Path] = []
    for i in range(20):
        vpath = OUTPUT_DIR / f"{job_prefix}_s{i}.mp4"
        if vpath.exists():
            video_files.append(vpath)
        else:
            break

    keyframes: list[Path] = []
    for i in range(20):
        kpath = COMFYUI_DIR / f"storyboard_{job_prefix}_s{i}.png"
        if kpath.exists():
            keyframes.append(kpath)
        else:
            break

    # Detect source clip fps; cap resolution to 1280x720 for ARM64 stability
    # (Chromium on RPi5 crashes at 1920x1080 with multiple OffthreadVideo)
    MAX_RENDER_W, MAX_RENDER_H = 1280, 720
    if video_files:
        probe = await _get_video_info(str(video_files[0]))
        source_fps = round(probe.get("fps", 24))
        if source_fps > 0:
            fps = source_fps
    width, height = MAX_RENDER_W, MAX_RENDER_H
    print(f"[montage] Render target: {width}x{height}@{fps}fps (ARM64 safe)", flush=True)

    if not video_files and not keyframes:
        note = "No video clips or keyframes found for montage"
        print(f"[montage] {note}", flush=True)
        kitsu_result = await _kitsu_step_task(job, "Montage", "done", note)
        await _notify_step_completed(job, "montage")
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, extras

    music_path = OUTPUT_DIR / f"{job_prefix}-music.wav"
    vo_path = OUTPUT_DIR / f"{job_prefix}-kokoro-vo.wav"
    srt_path = OUTPUT_DIR / f"{job_prefix}-subtitles.srt"

    # --- Phase 2: Normalize clips + copy to creative-assets ---
    # Re-encode clips to match composition fps/resolution to avoid
    # Chromium ARM64 decode artifacts (black pixel blocks).
    assets_dir = CREATIVE_ASSETS_DIR / job_prefix
    assets_dir.mkdir(parents=True, exist_ok=True)

    normalized_video_files: list[Path] = []
    for vf in video_files:
        dest = assets_dir / vf.name
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", str(vf),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-r", str(fps),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",  # strip audio (Remotion handles audio separately)
                str(dest),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120)
            if dest.exists() and dest.stat().st_size > 0:
                normalized_video_files.append(dest)
                print(f"[montage] Normalized {vf.name} → {width}x{height}@{fps}fps", flush=True)
            else:
                shutil.copy2(vf, dest)
                normalized_video_files.append(dest)
                print(f"[montage] Normalize failed for {vf.name}, using original", flush=True)
        except (asyncio.TimeoutError, OSError) as e:
            shutil.copy2(vf, dest)
            normalized_video_files.append(dest)
            print(f"[montage] Normalize timeout {vf.name}: {e}", flush=True)

    video_files = normalized_video_files

    for src in keyframes:
        shutil.copy2(src, assets_dir / src.name)
    for src in [music_path, vo_path]:
        if src.exists():
            shutil.copy2(src, assets_dir / src.name)

    # --- Phase 3: Build scenes[] ---
    scene_prompts = job.get("scene_prompts", [])
    scenes: list[dict[str, Any]] = []
    remotion_base = REMOTION_URL or "http://workstation_remotion:3200"

    for i in range(max(len(video_files), len(keyframes), len(scene_prompts))):
        sp = scene_prompts[i] if i < len(scene_prompts) else {}
        duration_sec = sp.get("duration_seconds", 5)
        duration_frames = int(duration_sec * fps)
        camera_movement = sp.get("camera_movement", "")

        if i < len(video_files):
            scenes.append({
                "type": "video",
                "src": f"{remotion_base}/creative-assets/{job_prefix}/{video_files[i].name}",
                "durationInFrames": duration_frames,
                "sceneIndex": i,
            })
        elif i < len(keyframes):
            scenes.append({
                "type": "keyframe",
                "src": f"{remotion_base}/creative-assets/{job_prefix}/{keyframes[i].name}",
                "durationInFrames": duration_frames,
                "sceneIndex": i,
                "kenBurns": _camera_movement_to_ken_burns(camera_movement),
            })

    if not scenes:
        note = "No renderable scenes"
        kitsu_result = await _kitsu_step_task(job, "Montage", "done", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, extras

    # --- Phase 4: Parse SRT ---
    subtitles: list[dict[str, Any]] = []
    if srt_path.exists():
        try:
            subtitles = _parse_srt(srt_path.read_text())
            print(f"[montage] Parsed {len(subtitles)} subtitle lines", flush=True)
        except Exception as srt_exc:
            print(f"[montage] SRT parse error: {srt_exc}", flush=True)

    # --- Phase 5: Build inputProps ---
    direction = job.get("direction", _DEFAULT_DIRECTION)
    title = job.get("title", "")
    width, height = 1920, 1080
    try:
        res = job.get("resolution", "1920x1080")
        width, height = [int(x) for x in res.split("x")]
    except (ValueError, AttributeError):
        pass

    input_props: dict[str, Any] = {
        "scenes": scenes,
        "direction": direction,
        "fps": fps,
        "width": width,
        "height": height,
    }

    # Title card
    if title:
        input_props["title"] = {
            "text": title,
            "color": direction.get("typography", {}).get("textColor", "#ffffff"),
            "backgroundColor": "#0f0f0f",
            "durationInFrames": int(3 * fps),
            "animation": "typewriter" if "serif" in direction.get("typography", {}).get("fontFamily", "").lower() else "fade",
        }

    # Outro
    input_props["outro"] = {
        "text": title,
        "subtitle": "VPAI Creative Studio",
        "color": direction.get("typography", {}).get("textColor", "#ffffff"),
        "backgroundColor": "#0f0f0f",
        "durationInFrames": int(2 * fps),
        "animation": "fade",
    }

    # Subtitles
    if subtitles:
        input_props["subtitles"] = subtitles

    # Audio — static defaults (LLM direction does not control audio levels)
    audio: dict[str, Any] = {}
    if music_path.exists():
        audio["musicSrc"] = f"{remotion_base}/creative-assets/{job_prefix}/{music_path.name}"
        audio["musicVolume"] = 0.4
        audio["musicFadeInFrames"] = int(2 * fps)
        audio["musicFadeOutFrames"] = int(3 * fps)
    if vo_path.exists():
        audio["voiceoverSrc"] = f"{remotion_base}/creative-assets/{job_prefix}/{vo_path.name}"
        audio["voiceoverVolume"] = 0.9
    if audio:
        audio.setdefault("duckMusicOnVo", True)
        audio.setdefault("duckLevel", 0.2)
        audio.setdefault("musicVolume", 0.4)
        audio.setdefault("voiceoverVolume", 0.9)
        audio.setdefault("musicFadeInFrames", int(2 * fps))
        audio.setdefault("musicFadeOutFrames", int(3 * fps))
        input_props["audio"] = audio

    print(f"[montage] Built inputProps: {len(scenes)} scenes, "
          f"transition={direction.get('defaultTransition', '?')}, "
          f"grade={direction.get('colorGrade', {}).get('preset', '?')}", flush=True)

    # --- Phase 6: Call Remotion ---
    output_path = OUTPUT_DIR / f"{job_prefix}_final.mp4"
    remotion_ok = False

    if REMOTION_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{REMOTION_URL}/renders",
                    json={"compositionId": "Montage", "inputProps": input_props},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        print("[montage] Remotion queue full, falling back to ffmpeg", flush=True)
                    elif resp.status != 200:
                        body = await resp.text()
                        print(f"[montage] Remotion submit error {resp.status}: {body[:200]}", flush=True)
                    else:
                        render_data = await resp.json()
                        render_job_id = render_data.get("jobId", "")
                        print(f"[montage] Remotion job: {render_job_id}", flush=True)

                        # Poll for completion (5s intervals, 600s timeout)
                        for poll_i in range(120):
                            await asyncio.sleep(5)
                            async with session.get(
                                f"{REMOTION_URL}/renders/{render_job_id}",
                                timeout=aiohttp.ClientTimeout(total=10),
                            ) as poll_resp:
                                poll_data = await poll_resp.json()
                                status = poll_data.get("status", "")
                                if poll_i % 6 == 0:
                                    progress = poll_data.get("progress", 0)
                                    print(f"[montage] Remotion poll {poll_i}: {status} "
                                          f"progress={progress:.0%}", flush=True)
                                if status == "completed":
                                    video_url = poll_data.get("videoUrl", "")
                                    if video_url:
                                        async with session.get(
                                            video_url,
                                            timeout=aiohttp.ClientTimeout(total=60),
                                        ) as dl_resp:
                                            if dl_resp.status == 200:
                                                final_bytes = await dl_resp.read()
                                                output_path.write_bytes(final_bytes)
                                                remotion_ok = True
                                                print(f"[montage] Remotion render OK: "
                                                      f"{len(final_bytes)} bytes", flush=True)
                                    break
                                elif status == "failed":
                                    err = poll_data.get("error", "unknown")
                                    print(f"[montage] Remotion render failed: {err}", flush=True)
                                    break
        except Exception as exc:
            print(f"[montage] Remotion error: {exc}", flush=True)

    # --- Phase 7: Fallback ffmpeg ---
    if not remotion_ok:
        if video_files:
            print("[montage] Falling back to ffmpeg concat", flush=True)
            fallback_path = await _montage_ffmpeg_fallback(job_prefix, video_files)
            if fallback_path:
                output_path = fallback_path
            else:
                note = "Both Remotion and ffmpeg failed"
                kitsu_result = await _kitsu_step_task(job, "Montage", "wfa", note)
                await _notify_step_completed(job, "montage")
                return {"status": "error", "note": note, "kitsu": kitsu_result}, extras

    # --- Phase 8: Kitsu + Telegram ---
    if output_path.exists():
        final_size = output_path.stat().st_size
        extras["montage_path"] = str(output_path)
        extras["montage_size"] = final_size
        extras["remotion_rendered"] = remotion_ok
        total_duration = sum(
            sp.get("duration_seconds", 5) for sp in scene_prompts
        ) if scene_prompts else len(video_files) * 5
        render_method = "Remotion" if remotion_ok else "ffmpeg"
        note = (
            f"Montage ({render_method}): {len(scenes)} scenes, "
            f"{final_size / 1024 / 1024:.1f} MB, ~{total_duration}s total."
        )
        print(f"[montage] {note}", flush=True)

        # Upload to Kitsu
        project_id = job.get("kitsu_project_id", "")
        overview_shot = job.get("kitsu_overview_shot_id", "")
        if project_id and overview_shot and KITSU_URL:
            try:
                async with aiohttp.ClientSession() as ks:
                    mt_type_id = await _kitsu_get_task_type_id(ks, "Montage")
                    mt_task = await _kitsu_get_or_create_task(
                        ks, overview_shot, mt_type_id, project_id,
                    )
                    if mt_task:
                        wfa_id = await _kitsu_get_status_id(ks, "wfa")
                        await _kitsu_post_comment(ks, mt_task["id"], wfa_id, note)
            except Exception as ke:
                print(f"[montage] Kitsu error: {ke}", flush=True)

        # Telegram
        if final_size < 50 * 1024 * 1024:
            video_bytes = output_path.read_bytes()
            await _notify_step_completed(job, "montage", video_bytes=video_bytes)
        else:
            await _notify_step_completed(job, "montage")
    else:
        note = "No output file produced"
        print(f"[montage] {note}", flush=True)

    kitsu_result = await _kitsu_step_task(job, "Montage", "wfa", note)
    return {"status": "ok", "note": note, "render_method": "remotion" if remotion_ok else "ffmpeg", "kitsu": kitsu_result}, extras


async def _step_subtitles(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle subtitles step: whisper.cpp local transcription."""
    skip = params.get("skip", False)
    if skip:
        kitsu_result = await _kitsu_step_task(job, "Sous-titres", "done", "Skipped by user")
        return {"status": "ok", "note": "Skipped", "kitsu": kitsu_result}, {}
    if job.get("remotion_rendered"):
        kitsu_result = await _kitsu_step_task(job, "Sous-titres", "done", "Integrated in Remotion montage")
        return {"status": "ok", "note": "Handled by Remotion montage", "kitsu": kitsu_result}, {}

    language = params.get("language", "fr")
    # Find the voiceover audio or source video
    vo_path = OUTPUT_DIR / f"{job['job_id'][:8]}-kokoro-vo.wav"
    src_video = WATCH_DIR / job.get("source_filename", "")

    audio_input = str(vo_path) if vo_path.exists() else str(src_video)
    if not Path(audio_input).exists():
        note = "No audio source found for transcription"
        kitsu_result = await _kitsu_step_task(job, "Sous-titres", "done", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}

    try:
        srt_path = OUTPUT_DIR / f"{job['job_id'][:8]}-subtitles.srt"
        # whisper.cpp outputs SRT with --output-srt flag
        proc = await asyncio.create_subprocess_exec(
            "whisper-cpp",
            "-m", "/opt/whisper.cpp/models/ggml-base.bin",
            "-l", language,
            "--output-srt",
            "-of", str(srt_path.with_suffix("")),  # whisper adds .srt
            "-f", audio_input,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        actual_srt = srt_path.with_suffix(".srt") if not srt_path.exists() else srt_path

        if actual_srt.exists():
            note = f"Subtitles generated: {actual_srt.name} ({language})"
        else:
            note = f"whisper.cpp ran but no SRT output. stderr: {stderr.decode()[:200]}"
    except FileNotFoundError:
        note = "whisper-cpp not found in container — install whisper.cpp"
    except Exception as exc:
        note = f"Subtitles failed: {exc}"

    kitsu_result = await _kitsu_step_task(job, "Sous-titres", "done", note)
    return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}


async def _step_colorgrade(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle colorgrade step: ffmpeg LUT application."""
    if job.get("remotion_rendered"):
        kitsu_result = await _kitsu_step_task(job, "Color Grade", "done", "Integrated in Remotion montage")
        return {"status": "ok", "note": "Handled by Remotion montage", "kitsu": kitsu_result}, {}
    lut_name = params.get("lut", "teal-orange")
    contrast = params.get("contrast", "1.0")

    lut_path = Path(f"/app/luts/{lut_name}.cube")
    if not lut_path.exists():
        available = [f.stem for f in Path("/app/luts").glob("*.cube")]
        note = f"LUT '{lut_name}' not found. Available: {', '.join(available)}"
        kitsu_result = await _kitsu_step_task(job, "Color Grade", "wfa", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}

    # Find the latest video output to grade
    montage_path = OUTPUT_DIR / f"{job['job_id'][:8]}-montage.mp4"
    if not montage_path.exists():
        # Fallback: try any video in output
        videos = list(OUTPUT_DIR.glob(f"{job['job_id'][:8]}*.mp4"))
        montage_path = videos[0] if videos else None

    if not montage_path or not montage_path.exists():
        note = f"No video found to color grade. Run montage step first."
        kitsu_result = await _kitsu_step_task(job, "Color Grade", "wfa", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}

    graded_path = OUTPUT_DIR / f"{job['job_id'][:8]}-graded.mp4"
    try:
        cmd = [
            "ffmpeg", "-i", str(montage_path),
            "-vf", f"lut3d=file={lut_path},eq=contrast={contrast}",
            "-c:a", "copy",
            "-y", str(graded_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if graded_path.exists():
            note = f"Color graded with {lut_name} (contrast={contrast}): {graded_path.name}"
        else:
            note = f"ffmpeg grading failed: {stderr.decode()[-200:]}"
    except Exception as exc:
        note = f"Color grade error: {exc}"

    kitsu_result = await _kitsu_step_task(job, "Color Grade", "wfa", note)
    return {"status": "ok", "note": note, "lut": lut_name, "kitsu": kitsu_result}, {}


async def _step_review(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle review step: send Telegram notification, create Kitsu playlist."""
    title = job.get("title", "Unknown")
    job_id = job["job_id"]
    completed = len(job.get("steps_completed", []))
    total = len(PIPELINE_STEPS)

    # Send Telegram notification
    camera = job.get("camera", "")
    lens = job.get("lens", "")
    cam_info = f"\n🎥 Camera: {camera} | Lens: {lens}" if camera else ""
    kitsu_base = KITSU_URL or "https://boss.ewutelo.cloud"
    msg = (
        f"🎬 *Review needed*\n\n"
        f"📽 Production: *{title}*{cam_info}\n"
        f"📊 Progress: {completed}/{total} steps completed\n"
        f"🔗 [Ouvrir dans Kitsu]({kitsu_base})\n\n"
        f"Job: `{job.get('slug', job_id[:12])}`"
    )
    telegram_ok = await _send_telegram(msg)

    # Create Kitsu playlist
    playlist_result: dict[str, Any] = {}
    if KITSU_URL and KITSU_TOKEN and job.get("kitsu_project_id"):
        async with aiohttp.ClientSession() as session:
            playlist = await _kitsu_create_playlist(
                session,
                job["kitsu_project_id"],
                f"Review: {title}",
                job.get("kitsu_shot_ids", []),
            )
            if playlist:
                playlist_result = {"playlist_id": playlist.get("id", "")}

    kitsu_result = await _kitsu_step_task(
        job, "Review", "wfa",
        f"Review requested. Telegram: {'sent' if telegram_ok else 'not configured'}",
    )

    return {
        "status": "ok",
        "telegram_sent": telegram_ok,
        "playlist": playlist_result,
        "kitsu": kitsu_result,
    }, {}


async def _step_export(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle export step: ffmpeg final encode (video + audio + subtitles)."""
    if job.get("remotion_rendered") and "gif" not in params.get("formats", ""):
        kitsu_result = await _kitsu_step_task(job, "Export", "done", "Final render by Remotion montage")
        return {"status": "ok", "note": "Handled by Remotion montage", "kitsu": kitsu_result}, {}
    formats = params.get("formats", "mp4").split(",")
    job_prefix = job["job_id"][:8]

    # Find best available video (graded > montage > any)
    video = None
    for candidate in [f"{job_prefix}-graded.mp4", f"{job_prefix}-montage.mp4"]:
        p = OUTPUT_DIR / candidate
        if p.exists():
            video = p
            break
    if not video:
        videos = sorted(OUTPUT_DIR.glob(f"{job_prefix}*.mp4"))
        video = videos[-1] if videos else None

    if not video:
        note = "No video found for export. Complete previous steps first."
        kitsu_result = await _kitsu_step_task(job, "Export", "done", note)
        return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}

    # Best practice 2026: auto-upscale to target resolution if needed
    target_res = job.get("resolution", "1920x1080")
    upscale_result: dict[str, Any] = {}
    try:
        target_w, target_h = [int(x) for x in target_res.split("x")]
        # Check current video resolution
        probe = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(video),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await probe.communicate()
        vinfo = json.loads(stdout).get("streams", [{}])[0]
        cur_w = int(vinfo.get("width", target_w))
        cur_h = int(vinfo.get("height", target_h))

        if cur_w < target_w or cur_h < target_h:
            # Upscale via Composer (Upscaler_fal or local)
            upscale_model = await _composer_select_model(
                "upscale enhance resolution video", params.get("budget", "balanced"),
            )
            if upscale_model and upscale_model["node"].endswith("_fal"):
                upscale_result = {"model": upscale_model["name"],
                                  "from": f"{cur_w}x{cur_h}", "to": target_res,
                                  "note": "Submitted to fal.ai upscaler"}
            else:
                # Local ffmpeg scale (lanczos, free)
                upscaled = OUTPUT_DIR / f"{job_prefix}-upscaled.mp4"
                up_cmd = [
                    "ffmpeg", "-i", str(video),
                    "-vf", f"scale={target_w}:{target_h}:flags=lanczos",
                    "-c:v", "libx264", "-crf", "18", "-y", str(upscaled),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *up_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
                if upscaled.exists():
                    video = upscaled  # Use upscaled version
                    upscale_result = {"method": "ffmpeg_lanczos",
                                      "from": f"{cur_w}x{cur_h}", "to": target_res}
    except Exception as exc:
        upscale_result = {"error": str(exc)}

    results: list[dict[str, Any]] = []
    for fmt in formats:
        fmt = fmt.strip()
        slug = job.get("slug", job.get("title", "export")).replace(" ", "_")
        out_name = f"{slug}-final.{fmt}"
        out_path = OUTPUT_DIR / out_name

        try:
            cmd = ["ffmpeg", "-i", str(video)]

            # Mux audio if available
            music = OUTPUT_DIR / f"{job_prefix}-music.wav"
            vo = OUTPUT_DIR / f"{job_prefix}-kokoro-vo.wav"
            if music.exists():
                cmd.extend(["-i", str(music)])
            if vo.exists():
                cmd.extend(["-i", str(vo)])

            # Burn-in subtitles if SRT exists
            srt = OUTPUT_DIR / f"{job_prefix}-subtitles.srt"
            if srt.exists():
                cmd.extend(["-vf", f"subtitles={srt}"])

            if fmt == "gif":
                cmd.extend([
                    "-vf", "fps=10,scale=480:-1:flags=lanczos",
                    "-y", str(out_path),
                ])
            else:
                cmd.extend(["-c:v", "libx264", "-crf", "23", "-y", str(out_path)])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if out_path.exists():
                size_mb = out_path.stat().st_size / (1024 * 1024)
                results.append({"format": fmt, "path": str(out_path), "size_mb": round(size_mb, 2)})
        except Exception as exc:
            results.append({"format": fmt, "error": str(exc)})

    upscale_note = f" Upscaled: {upscale_result.get('from', '?')}→{upscale_result.get('to', '?')}" if upscale_result and "error" not in upscale_result else ""
    note = f"Exported: {', '.join(r.get('path', r.get('error', '?')).split('/')[-1] for r in results)}.{upscale_note}"
    kitsu_result = await _kitsu_step_task(job, "Export", "done", note)
    return {"status": "ok", "exports": results, "upscale": upscale_result, "kitsu": kitsu_result}, {}


async def _step_publish(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle publish step: placeholder."""
    skip = params.get("skip", False)
    note = "Skipped by user" if skip else "Not yet implemented -- manual step"
    kitsu_result = await _kitsu_step_task(job, "Publication", "done", note)
    return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}


STEP_HANDLERS = {
    "brief": _step_brief,
    "research": _step_research,
    "script": _step_script,
    "storyboard": _step_storyboard,
    "voiceover": _step_voiceover,
    "music": _step_music,
    "imagegen": _step_imagegen,
    "videogen": _step_videogen,
    "montage": _step_montage,
    "subtitles": _step_subtitles,
    "colorgrade": _step_colorgrade,
    "review": _step_review,
    "export": _step_export,
    "publish": _step_publish,
}


async def _kitsu_step_task(
    job: dict[str, Any],
    task_type_name: str,
    target_status: str,
    comment_text: str,
    cost_usd: float = 0.0,
    cast_asset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create/update a Kitsu task for a pipeline step on the sequence.

    Enhanced with:
    - cost_usd: set estimation on task (visible in schedule/budget)
    - cast_asset_ids: link assets to the sequence (breakdown/casting)
    """
    if not KITSU_URL or not KITSU_TOKEN:
        return {"skipped": "KITSU not configured"}

    shot_id = job.get("kitsu_overview_shot_id", "")
    project_id = job.get("kitsu_project_id", "")
    if not shot_id or not project_id:
        return {"skipped": "No Kitsu shot in job"}

    try:
        async with aiohttp.ClientSession() as session:
            task_type_id = await _kitsu_get_task_type_id(session, task_type_name)
            task = await _kitsu_get_or_create_task(
                session, shot_id, task_type_id, project_id,
            )
            status_id = await _kitsu_get_status_id(session, target_status)
            comment = await _kitsu_post_comment(
                session, task["id"], status_id, comment_text[:5000],
            )

            # Set estimation (cost → visible in Kitsu schedule)
            if cost_usd > 0:
                await _kitsu_set_task_estimation(
                    session, task["id"], cost_usd=cost_usd,
                )

            # Cast assets into shots (breakdown links)
            cast_count = 0
            if cast_asset_ids:
                for shot_id in job.get("kitsu_shot_ids", []):
                    for asset_id in cast_asset_ids:
                        ok = await _kitsu_cast_asset_to_shot(
                            session, project_id, shot_id, asset_id,
                        )
                        if ok:
                            cast_count += 1

            result: dict[str, Any] = {
                "task_id": task["id"],
                "comment_id": comment.get("id", "") if comment else "",
                "status": target_status,
            }
            if cost_usd > 0:
                result["estimation_usd"] = cost_usd
            if cast_count > 0:
                result["cast_links"] = cast_count
            return result
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# HTTP API handlers (existing)
# ============================================================
async def health(request: web.Request) -> web.Response:
    """GET /health -- service health check."""
    return web.json_response({
        "status": "ok",
        "version": VERSION,
        "integrations": {
            "litellm": bool(LITELLM_URL),
            "kitsu": bool(KITSU_URL),
            "qdrant": bool(QDRANT_URL),
            "gitea": bool(GITEA_URL),
            "n8n_creative": bool(N8N_CREATIVE_PIPELINE_URL),
        },
    })


async def list_jobs(request: web.Request) -> web.Response:
    """GET /api/jobs -- list completed analysis results."""
    analyzed = []
    if OUTPUT_DIR.exists():
        analyzed = [f.name for f in OUTPUT_DIR.iterdir() if f.is_file() and f.suffix == ".json"]
    return web.json_response({"analyzed": analyzed, "count": len(analyzed)})


async def list_watch(request: web.Request) -> web.Response:
    """GET /api/watch -- list files in watch directory."""
    files = []
    if WATCH_DIR.exists():
        files = [f.name for f in WATCH_DIR.iterdir() if f.is_file()]
    return web.json_response({"files": files, "count": len(files)})


async def analyze(request: web.Request) -> web.Response:
    """POST /api/analyze -- run multi-scene analysis pipeline."""
    data = await request.json()
    filename = data.get("filename", "")
    template_name = data.get("template", "default")

    if not filename:
        return web.json_response({"error": "filename required"}, status=400)

    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response({"error": f"File not found: {filename}"}, status=404)

    result = await run_analysis(filename, template_name)

    out = OUTPUT_DIR / f"{Path(filename).stem}.json"
    out.write_text(json.dumps(result, indent=2))
    return web.json_response(result)


async def webhook_metube(request: web.Request) -> web.Response:
    """POST /api/webhook/metube -- auto-trigger analysis on MeTube download."""
    data = await request.json()
    filename = data.get("filename", "")
    if not filename:
        return web.json_response({"error": "No filename"}, status=400)

    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response(
            {"error": f"File not found: {filename}", "received": data}, status=404,
        )

    asyncio.create_task(_background_analyze(filename))
    return web.json_response({"status": "queued", "filename": filename})


async def _background_analyze(filename: str) -> None:
    """Run full analysis in background after webhook trigger."""
    result = await run_analysis(filename)
    out = OUTPUT_DIR / f"{Path(filename).stem}.json"
    out.write_text(json.dumps(result, indent=2))


# ============================================================
# Agent-friendly API: search, get, remix
# ============================================================
async def search_assets(request: web.Request) -> web.Response:
    """GET /api/assets?style=X&mood=Y&q=Z -- search VideoRef assets."""
    if not KITSU_URL or not KITSU_TOKEN:
        return web.json_response({"error": "KITSU not configured"}, status=503)

    q = request.query.get("q", "").lower()
    style_filter = request.query.get("style", "").lower()
    mood_filter = request.query.get("mood", "").lower()
    motion_filter = request.query.get("motion", "").lower()
    limit = int(request.query.get("limit", "20"))

    try:
        async with aiohttp.ClientSession() as session:
            project = await _kitsu_get_asset_library(session)
            assets = await _kitsu_api(
                session, "GET",
                f"/data/projects/{project['id']}/assets",
            )

            results = []
            for a in (assets or []):
                data = a.get("data") or {}
                name = a.get("name", "").lower()
                desc = a.get("description", "").lower()
                prompt = data.get("ai_prompt", "").lower()
                style = data.get("style", "").lower()
                mood = data.get("mood", "").lower()
                motion = data.get("motion", "").lower()

                # Apply filters
                if style_filter and style_filter not in style:
                    continue
                if mood_filter and mood_filter not in mood:
                    continue
                if motion_filter and motion_filter != motion:
                    continue
                if q and q not in name and q not in desc and q not in prompt and q not in style:
                    continue

                results.append({
                    "id": a["id"],
                    "name": a["name"],
                    "style": data.get("style", ""),
                    "mood": data.get("mood", ""),
                    "colors": data.get("colors", ""),
                    "motion": data.get("motion", ""),
                    "ai_prompt": data.get("ai_prompt", ""),
                    "description": a.get("description", "")[:200],
                })
                if len(results) >= limit:
                    break

            return web.json_response({
                "assets": results,
                "count": len(results),
                "total": len(assets or []),
            })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def get_asset(request: web.Request) -> web.Response:
    """GET /api/assets/{id} -- get full asset details with prompt."""
    asset_id = request.match_info["id"]
    if not KITSU_URL or not KITSU_TOKEN:
        return web.json_response({"error": "KITSU not configured"}, status=503)

    try:
        async with aiohttp.ClientSession() as session:
            asset = await _kitsu_api(
                session, "GET", f"/data/entities/{asset_id}",
            )
            if not asset:
                return web.json_response({"error": "Asset not found"}, status=404)

            data = asset.get("data") or {}
            return web.json_response({
                "id": asset["id"],
                "name": asset.get("name", ""),
                "description": asset.get("description", ""),
                "style": data.get("style", ""),
                "mood": data.get("mood", ""),
                "colors": data.get("colors", ""),
                "motion": data.get("motion", ""),
                "ai_prompt": data.get("ai_prompt", ""),
                "preview_file_id": asset.get("preview_file_id"),
                "has_avatar": asset.get("has_avatar"),
                "created_at": asset.get("created_at", ""),
            })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def semantic_search(request: web.Request) -> web.Response:
    """GET /api/search?q=cinematic+dramatic+blue -- semantic search via Qdrant."""
    query = request.query.get("q", "")
    limit = int(request.query.get("limit", "5"))
    if not query:
        return web.json_response({"error": "q parameter required"}, status=400)
    if not QDRANT_URL or not LITELLM_URL:
        return web.json_response({"error": "Search not configured"}, status=503)

    try:
        results = await _search_qdrant(query, limit)
        formatted = [
            {
                "score": round(r.get("score", 0), 3),
                "filename": r.get("filename", ""),
                "style": r.get("style", ""),
                "mood": r.get("mood", ""),
                "colors": r.get("colors", []),
                "suggested_prompt": r.get("suggested_prompt", ""),
            }
            for r in results
        ]
        return web.json_response({
            "query": query,
            "results": formatted,
            "count": len(formatted),
        })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def remix(request: web.Request) -> web.Response:
    """POST /api/remix -- remix an existing VideoRef asset with modifications.

    Body supports optional camera/lens/aperture/motion params for camera tokens.
    """
    data = await request.json()
    asset_id = data.get("asset_id", "")
    source_prompt = data.get("source_prompt", "")
    modifications = data.get("modifications", {})
    template_name = data.get("template", "default")
    output_name = data.get("output_name", "remix")
    camera = data.get("camera", "")
    lens = data.get("lens", "")
    aperture = data.get("aperture", "")
    motion_param = data.get("motion", "")

    # Get source prompt from Kitsu asset or direct input
    original_analysis = {}
    if asset_id and KITSU_URL and KITSU_TOKEN:
        try:
            async with aiohttp.ClientSession() as session:
                asset = await _kitsu_api(
                    session, "GET", f"/data/entities/{asset_id}",
                )
                asset_data = asset.get("data") or {}
                source_prompt = asset_data.get("ai_prompt", "")
                original_analysis = {
                    "style": asset_data.get("style", ""),
                    "mood": asset_data.get("mood", ""),
                    "colors": asset_data.get("colors", ""),
                    "motion": asset_data.get("motion", ""),
                    "suggested_prompt": source_prompt,
                    "source_asset": asset.get("name", ""),
                }
        except Exception as exc:
            return web.json_response(
                {"error": f"Failed to fetch asset: {exc}"}, status=404,
            )

    if not source_prompt:
        return web.json_response(
            {"error": "Provide asset_id or source_prompt"}, status=400,
        )

    # Inject camera tokens
    source_prompt = _inject_camera_tokens(
        source_prompt, camera, lens, aperture, motion_param,
    )

    # Build remix prompt via LiteLLM
    mod_parts = []
    for key, value in modifications.items():
        mod_parts.append(f"- Change {key}: {value}")
    mod_text = "\n".join(mod_parts) if mod_parts else "No modifications"

    remix_prompt = source_prompt
    if modifications and LITELLM_URL:
        try:
            async with aiohttp.ClientSession() as session:
                llm_prompt = (
                    f"You are a prompt engineer for AI image generation. "
                    f"Take this original prompt and apply the modifications below. "
                    f"Return ONLY the modified prompt, nothing else.\n\n"
                    f"Original prompt:\n{source_prompt}\n\n"
                    f"Modifications:\n{mod_text}\n\n"
                    f"Modified prompt:"
                )
                async with session.post(
                    f"{LITELLM_URL}/v1/chat/completions",
                    json={
                        "model": "claude-sonnet",
                        "messages": [{"role": "user", "content": llm_prompt}],
                        "max_tokens": 500,
                    },
                    headers={
                        "Authorization": f"Bearer {LITELLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        llm_data = await resp.json()
                        remix_prompt = llm_data["choices"][0]["message"]["content"].strip()
        except Exception:
            pass  # Fall back to original prompt

    # Apply style/colors overrides
    remixed_analysis = dict(original_analysis)
    remixed_analysis["suggested_prompt"] = remix_prompt
    remixed_analysis["negative_prompt"] = original_analysis.get("negative_prompt", "blurry, low quality")
    if modifications.get("style"):
        remixed_analysis["style"] = modifications["style"]
    if modifications.get("mood"):
        remixed_analysis["mood"] = modifications["mood"]

    # Generate workflow from template
    colors = (modifications.get("colors") or original_analysis.get("colors", "")).split(", ")
    template = await fetch_template(template_name)
    workflow = generate_workflow(template, remixed_analysis, colors)

    # Save workflow
    wf_path = COMFYUI_DIR / f"{output_name}_workflow.json"
    wf_path.write_text(json.dumps(workflow, indent=2))

    return web.json_response({
        "status": "ok",
        "original_prompt": source_prompt[:300],
        "remixed_prompt": remix_prompt[:500],
        "modifications_applied": modifications,
        "camera_tokens": {"camera": camera, "lens": lens, "aperture": aperture, "motion": motion_param},
        "style": remixed_analysis.get("style", ""),
        "mood": remixed_analysis.get("mood", ""),
        "template": template_name,
        "workflow_path": str(wf_path),
        "workflow": workflow,
    })


# ============================================================
# Production pipeline API endpoints
# ============================================================
async def get_cameras(request: web.Request) -> web.Response:
    """GET /api/cameras -- return available camera presets."""
    presets = await _load_camera_presets()
    return web.json_response(presets)


async def produce_start(request: web.Request) -> web.Response:
    """POST /api/produce/start -- start a new production job.

    Body: {"title": "...", "url": "...", "camera": "ARRI", "lens": "anamorphic", ...}
    """
    data = await request.json()
    title = data.get("title", "")
    if not title:
        return web.json_response({"error": "title required"}, status=400)

    job = _new_job(
        title=title,
        url=data.get("url", ""),
        camera=data.get("camera", ""),
        lens=data.get("lens", ""),
        aperture=data.get("aperture", ""),
        motion=data.get("motion", ""),
        fps=data.get("fps", "24"),
        format=data.get("format", "landscape"),
        style=data.get("style", "2d3d"),
    )
    # Kitsu project is created by _step_brief (not here)
    # to avoid duplicate name errors when brief also creates it.
    _save_job(job)

    return web.json_response({
        "status": "created",
        "job_id": job["job_id"],
        "slug": job["slug"],
        "title": job["title"],
        "note": "Kitsu project will be created at Brief step",
        "pipeline_steps": STEP_IDS,
        "next_step": STEP_IDS[0],
    })


async def produce_step(request: web.Request) -> web.Response:
    """POST /api/produce/step -- advance to next pipeline step.

    Body: {"job_id": "...", "step": "brief", "params": {...}}
    """
    data = await request.json()
    job_id = data.get("job_id", "")
    step_id = data.get("step", "")
    # Params can be nested in "params" key OR flat in body (CLI sends flat)
    params = data.get("params", {})
    # Merge top-level keys into params (skip control keys)
    for k, v in data.items():
        if k not in ("job_id", "step", "params") and k not in params:
            params[k] = v

    if not job_id:
        return web.json_response({"error": "job_id required"}, status=400)
    if step_id not in STEP_MAP:
        return web.json_response(
            {"error": f"Unknown step: {step_id}. Valid: {STEP_IDS}"}, status=400,
        )

    job = _load_job(job_id)
    if job is None:
        return web.json_response({"error": f"Job not found: {job_id}"}, status=404)

    # Check step not already completed
    if step_id in job.get("steps_completed", []):
        return web.json_response(
            {"error": f"Step '{step_id}' already completed. Use /api/produce/retake to redo."},
            status=409,
        )

    handler = STEP_HANDLERS.get(step_id)
    if not handler:
        return web.json_response({"error": f"No handler for step: {step_id}"}, status=500)

    try:
        result, extras = await handler(job, params)
    except Exception as exc:
        return web.json_response({"error": f"Step failed: {exc}"}, status=500)

    updated_job = _advance_job(job, step_id, extras)
    _save_job(updated_job)

    return web.json_response({
        "status": "ok",
        "job_id": job_id,
        "step": step_id,
        "step_result": result,
        "steps_completed": updated_job["steps_completed"],
        "next_step": updated_job["current_step"],
    })


async def produce_retake(request: web.Request) -> web.Response:
    """POST /api/produce/retake -- retake a specific step.

    Body: {"job_id": "...", "step": "imagegen", "scenes": [3, 5], "modifications": {...}}
    """
    data = await request.json()
    job_id = data.get("job_id", "")
    step_id = data.get("step", "")
    scenes = data.get("scenes", [])
    modifications = data.get("modifications", {})

    if not job_id:
        return web.json_response({"error": "job_id required"}, status=400)
    if step_id not in STEP_MAP:
        return web.json_response(
            {"error": f"Unknown step: {step_id}. Valid: {STEP_IDS}"}, status=400,
        )

    job = _load_job(job_id)
    if job is None:
        return web.json_response({"error": f"Job not found: {job_id}"}, status=404)

    # Build params with retake info
    params = {
        "retake": True,
        "scenes": scenes,
        "modifications": modifications,
    }

    handler = STEP_HANDLERS.get(step_id)
    if not handler:
        return web.json_response({"error": f"No handler for step: {step_id}"}, status=500)

    try:
        result, extras = await handler(job, params)
    except Exception as exc:
        return web.json_response({"error": f"Retake failed: {exc}"}, status=500)

    # Update job without re-adding to completed (already there)
    if extras:
        updated_job = {**job, **extras}
    else:
        updated_job = dict(job)
    _save_job(updated_job)

    return web.json_response({
        "status": "ok",
        "job_id": job_id,
        "step": step_id,
        "retake": True,
        "scenes_retaken": scenes,
        "step_result": result,
    })


async def produce_status(request: web.Request) -> web.Response:
    """GET /api/produce/status/{job_id} -- get job status."""
    job_id = request.match_info["job_id"]
    job = _load_job(job_id)
    if job is None:
        return web.json_response({"error": f"Job not found: {job_id}"}, status=404)

    completed = job.get("steps_completed", [])
    total = len(PIPELINE_STEPS)
    progress = len(completed) / total if total > 0 else 0

    steps_detail = []
    for step in PIPELINE_STEPS:
        steps_detail.append({
            "id": step["id"],
            "task_type": step["task_type"],
            "needs_human": step["needs_human"],
            "optional": step["optional"],
            "completed": step["id"] in completed,
        })

    return web.json_response({
        "job_id": job["job_id"],
        "slug": job.get("slug", ""),
        "title": job["title"],
        "url": job.get("url", ""),
        "camera": job.get("camera", ""),
        "lens": job.get("lens", ""),
        "current_step": job.get("current_step"),
        "steps_completed": completed,
        "progress": round(progress, 2),
        "steps": steps_detail,
        "kitsu_project_id": job.get("kitsu_project_id", ""),
        "kitsu_sequence_id": job.get("kitsu_sequence_id", ""),
        "created_at": job.get("created_at", ""),
        "updated_at": job.get("updated_at", ""),
    })


# ============================================================
# App setup
# ============================================================
app = web.Application()
# Existing endpoints
app.router.add_get("/health", health)
app.router.add_get("/api/jobs", list_jobs)
app.router.add_get("/api/watch", list_watch)
app.router.add_get("/api/assets", search_assets)
app.router.add_get("/api/assets/{id}", get_asset)
app.router.add_get("/api/search", semantic_search)
app.router.add_post("/api/analyze", analyze)
app.router.add_post("/api/remix", remix)
app.router.add_post("/api/webhook/metube", webhook_metube)
# ============================================================
# 20. Transcription (whisper.cpp) + OCR (EasyOCR + Claude Vision)
# ============================================================
WHISPER_MODEL = "/opt/whisper.cpp/models/ggml-base.bin"
WHISPER_BIN = "whisper-cpp"
TRANSCRIPTS_DIR = OUTPUT_DIR / "transcripts"


async def _transcribe_audio(video_path: Path, language: str = "auto") -> dict:
    """Transcribe audio from video using whisper.cpp. Returns segments with timestamps."""
    import tempfile

    wav_file = Path(tempfile.mktemp(suffix=".wav"))
    try:
        # Extract audio as 16kHz mono WAV (whisper.cpp requirement)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", str(video_path),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            str(wav_file), "-y",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if not wav_file.exists() or wav_file.stat().st_size < 1000:
            return {"error": "Failed to extract audio", "segments": []}

        # Run whisper.cpp with JSON output
        cmd = [
            WHISPER_BIN,
            "-m", WHISPER_MODEL,
            "-f", str(wav_file),
            "--output-json-full",
            "--no-prints",
        ]
        if language != "auto":
            cmd.extend(["-l", language])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        # Parse whisper output (JSON on stdout)
        try:
            data = json.loads(stdout)
            segments = []
            for seg in data.get("transcription", []):
                segments.append({
                    "start": seg.get("timestamps", {}).get("from", ""),
                    "end": seg.get("timestamps", {}).get("to", ""),
                    "text": seg.get("text", "").strip(),
                })
            full_text = " ".join(s["text"] for s in segments)
            return {
                "segments": segments,
                "full_text": full_text,
                "language": data.get("result", {}).get("language", language),
                "segment_count": len(segments),
            }
        except json.JSONDecodeError:
            # Fallback: parse text output
            text = stdout.decode().strip()
            return {"segments": [], "full_text": text, "raw": True}
    finally:
        wav_file.unlink(missing_ok=True)


async def _ocr_frames(
    video_path: Path, interval_sec: int = 10, max_frames: int = 20,
) -> list[dict]:
    """Extract text from video frames using EasyOCR."""
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="vref_ocr_"))
    duration = _get_duration(video_path)
    fps_extract = max(1, duration // max_frames)

    # Extract frames at interval
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", str(video_path),
        "-vf", f"fps=1/{fps_extract}",
        "-frames:v", str(max_frames),
        "-q:v", "2",
        str(tmpdir / "ocr_%04d.jpg"), "-y",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    frames = sorted(tmpdir.glob("ocr_*.jpg"))
    if not frames:
        return []

    # OCR via Claude Vision (best quality, no local deps, no PyTorch bloat)
    results = []
    if LITELLM_URL and LITELLM_API_KEY:
        try:
            async with aiohttp.ClientSession() as session:
                for i, frame in enumerate(frames):
                    timestamp_sec = i * fps_extract
                    b64 = base64.b64encode(frame.read_bytes()).decode()

                    payload = {
                        "model": "claude-sonnet-4-20250514",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image_url",
                                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                {"type": "text",
                                 "text": "Extract ALL visible text from this image. "
                                         "Return JSON: {\"texts\": [{\"text\": \"...\", \"type\": \"title|code|ui|subtitle|other\"}]}. "
                                         "If no text visible, return {\"texts\": []}."},
                            ],
                        }],
                        "max_tokens": 512,
                    }

                    async with session.post(
                        f"{LITELLM_URL}/v1/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {LITELLM_API_KEY}",
                                 "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        try:
                            start = content.index("{")
                            end = content.rindex("}") + 1
                            parsed = json.loads(content[start:end])
                            texts = [
                                {"text": t["text"], "confidence": 0.95,
                                 "type": t.get("type", "other")}
                                for t in parsed.get("texts", []) if t.get("text")
                            ]
                        except (ValueError, json.JSONDecodeError):
                            texts = [{"text": content.strip(), "confidence": 0.8}] if content.strip() else []

                    if texts:
                        results.append({
                            "timestamp": f"{timestamp_sec // 60:02d}:{timestamp_sec % 60:02d}",
                            "timestamp_sec": timestamp_sec,
                            "texts": texts,
                        })
        except Exception as exc:
            results = [{"error": f"Vision OCR error: {exc}"}]
    else:
        results = [{"error": "LiteLLM not configured for Vision OCR"}]

    # Cleanup extracted frames
    try:
        for f in tmpdir.iterdir():
            f.unlink()
        tmpdir.rmdir()
    except Exception:
        pass

    return results


async def _extract_instructions(
    transcript: dict, ocr_results: list, video_name: str,
) -> dict:
    """Use Claude Vision via LiteLLM to extract structured instructions."""
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"error": "LiteLLM not configured"}

    full_text = transcript.get("full_text", "")[:3000]
    ocr_text = "\n".join(
        f"[{r['timestamp']}] {' | '.join(t['text'] for t in r.get('texts', []))}"
        for r in ocr_results[:15]
        if "timestamp" in r
    )[:2000]

    prompt = (
        f"Analyze this video content and extract structured information.\n\n"
        f"## Audio transcript:\n{full_text}\n\n"
        f"## On-screen text (OCR):\n{ocr_text}\n\n"
        f"Return JSON with:\n"
        f'{{"title": "...", "type": "tutorial|review|demo|vlog|other", '
        f'"language": "...", "summary": "2-3 sentences", '
        f'"instructions": ["step 1...", "step 2..."], '
        f'"tools_mentioned": ["tool1", "tool2"], '
        f'"key_timestamps": [{{"time": "MM:SS", "topic": "..."}}], '
        f'"code_snippets": ["snippet1"], '
        f'"tags": ["tag1", "tag2"]}}'
    )

    payload = {
        "model": "claude-sonnet-4-20250514",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LITELLM_URL}/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return {"error": f"LiteLLM {resp.status}: {body[:200]}"}
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                try:
                    start = content.index("{")
                    end = content.rindex("}") + 1
                    return json.loads(content[start:end])
                except (ValueError, json.JSONDecodeError):
                    return {"raw_analysis": content}
    except Exception as exc:
        return {"error": str(exc)}


async def transcribe_video(request: web.Request) -> web.Response:
    """POST /api/transcribe — Transcribe audio from a video file.

    Body: {"filename": "video.mp4", "language": "auto"}
    Returns: {"segments": [...], "full_text": "...", "language": "fr"}
    """
    data = await request.json()
    filename = data.get("filename", "")
    language = data.get("language", "auto")

    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response({"error": f"File not found: {filename}"}, status=404)

    transcript = await _transcribe_audio(src, language)

    # Save result
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    out = TRANSCRIPTS_DIR / f"{Path(filename).stem}_transcript.json"
    out.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))

    return web.json_response({
        "status": "ok",
        "filename": filename,
        "transcript": transcript,
        "saved_to": str(out),
    })


async def ocr_video(request: web.Request) -> web.Response:
    """POST /api/ocr — Extract on-screen text from video frames.

    Body: {"filename": "video.mp4", "interval": 10, "max_frames": 20}
    Returns: {"frames": [{"timestamp": "00:10", "texts": [...]}]}
    """
    data = await request.json()
    filename = data.get("filename", "")
    interval = data.get("interval", 10)
    max_frames = data.get("max_frames", 20)

    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response({"error": f"File not found: {filename}"}, status=404)

    ocr_results = await _ocr_frames(src, interval, max_frames)

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    out = TRANSCRIPTS_DIR / f"{Path(filename).stem}_ocr.json"
    out.write_text(json.dumps(ocr_results, indent=2, ensure_ascii=False))

    return web.json_response({
        "status": "ok",
        "filename": filename,
        "frame_count": len(ocr_results),
        "frames": ocr_results,
        "saved_to": str(out),
    })


async def video_intelligence(request: web.Request) -> web.Response:
    """POST /api/intelligence — Full video analysis: transcript + OCR + AI extraction.

    Body: {"filename": "video.mp4", "language": "auto", "store_kitsu": true}
    Returns: combined transcript + OCR + structured instructions
    """
    data = await request.json()
    filename = data.get("filename", "")
    language = data.get("language", "auto")
    store_kitsu = data.get("store_kitsu", True)

    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response({"error": f"File not found: {filename}"}, status=404)

    # Run transcript + OCR in parallel
    transcript_task = asyncio.create_task(_transcribe_audio(src, language))
    ocr_task = asyncio.create_task(_ocr_frames(src))

    transcript = await transcript_task
    ocr_results = await ocr_task

    # AI-powered instruction extraction
    instructions = await _extract_instructions(
        transcript, ocr_results, filename,
    )

    result = {
        "filename": filename,
        "transcript": transcript,
        "ocr": {"frame_count": len(ocr_results), "frames": ocr_results},
        "intelligence": instructions,
    }

    # Save full result
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    out = TRANSCRIPTS_DIR / f"{Path(filename).stem}_intelligence.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Store in Kitsu Asset Library + Qdrant
    kitsu_result = {}
    qdrant_result = {}

    if store_kitsu and KITSU_URL and KITSU_TOKEN:
        try:
            async with aiohttp.ClientSession() as session:
                library = await _kitsu_get_asset_library(session)
                entity_types = await _kitsu_api(session, "GET", "/data/entity-types")
                vref_type = next(
                    (t for t in entity_types if t["name"] == "VideoRef"), None,
                )
                if vref_type:
                    summary = instructions.get("summary", "")[:200]
                    video_type = instructions.get("type", "unknown")
                    tags = instructions.get("tags", [])

                    asset = await _kitsu_api(
                        session, "POST",
                        f"/data/projects/{library['id']}"
                        f"/asset-types/{vref_type['id']}/assets/new",
                        json_body={
                            "name": _generate_asset_name(
                                {"style": video_type,
                                 "mood": ", ".join(tags[:3]),
                                 "suggested_prompt": summary},
                                filename,
                            ) + "-Transcript",
                            "description": (
                                f"Type: {video_type}\n"
                                f"Summary: {summary}\n"
                                f"Language: {transcript.get('language', '?')}\n"
                                f"Segments: {transcript.get('segment_count', 0)}\n"
                                f"Tags: {', '.join(tags[:10])}"
                            ),
                            "data": {
                                "style": video_type,
                                "mood": ", ".join(tags[:5]),
                                "colors": "",
                                "motion": "low",
                                "ai_prompt": summary,
                            },
                        },
                    )
                    kitsu_result = {
                        "asset_id": asset.get("id", ""),
                        "asset_name": asset.get("name", ""),
                    }
        except Exception as exc:
            kitsu_result = {"error": str(exc)}

    if QDRANT_URL and QDRANT_API_KEY:
        try:
            text_to_embed = (
                f"{filename}: {instructions.get('summary', '')} "
                f"{transcript.get('full_text', '')[:500]}"
            )
            async with aiohttp.ClientSession() as session:
                # Get embedding
                async with session.post(
                    f"{LITELLM_URL}/v1/embeddings",
                    json={"model": "embedding", "input": text_to_embed[:8000]},
                    headers={
                        "Authorization": f"Bearer {LITELLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    emb_data = await resp.json()
                    vector = emb_data["data"][0]["embedding"]

                point_id = abs(hash(filename)) % (2**63)
                async with session.put(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points",
                    json={
                        "points": [{
                            "id": point_id,
                            "vector": vector,
                            "payload": {
                                "filename": filename,
                                "type": "transcript",
                                "summary": instructions.get("summary", ""),
                                "tags": instructions.get("tags", []),
                                "full_text": transcript.get("full_text", "")[:2000],
                                "source": "video-intelligence",
                            },
                        }],
                    },
                    headers={
                        "api-key": QDRANT_API_KEY,
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    qdrant_result = {"indexed": resp.status in (200, 201)}
        except Exception as exc:
            qdrant_result = {"error": str(exc)}

    result["kitsu"] = kitsu_result
    result["qdrant"] = qdrant_result
    result["saved_to"] = str(out)

    return web.json_response(result)


# New production pipeline endpoints
app.router.add_get("/api/cameras", get_cameras)
app.router.add_post("/api/produce/start", produce_start)
app.router.add_post("/api/produce/step", produce_step)
app.router.add_post("/api/produce/retake", produce_retake)
app.router.add_get("/api/produce/status/{job_id}", produce_status)
# Transcription + OCR endpoints
app.router.add_post("/api/transcribe", transcribe_video)
app.router.add_post("/api/ocr", ocr_video)
app.router.add_post("/api/intelligence", video_intelligence)

if __name__ == "__main__":
    for d in [OUTPUT_DIR, COMFYUI_DIR, JOBS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print(f"VideoRef Engine {VERSION} starting...")
    print(f"  WATCH_DIR: {WATCH_DIR}")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    print(f"  COMFYUI_DIR: {COMFYUI_DIR}")
    print(f"  JOBS_DIR: {JOBS_DIR}")
    print(f"  LITELLM: {'configured' if LITELLM_URL else 'NOT configured'}")
    print(f"  KITSU: {'configured' if KITSU_URL else 'NOT configured'}")
    print(f"  QDRANT: {'configured' if QDRANT_URL else 'NOT configured'}")
    print(f"  GITEA: {'configured' if GITEA_URL else 'NOT configured'}")
    print(f"  N8N_CREATIVE: {'configured' if N8N_CREATIVE_PIPELINE_URL else 'NOT configured'}")
    web.run_app(app, host="0.0.0.0", port=8082)
