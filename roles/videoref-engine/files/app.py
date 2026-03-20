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

COMFYUI_API_URL = os.environ.get("COMFYUI_API_URL", "http://workstation_comfyui:8188")
MODEL_REGISTRY_COLLECTION = "model-registry"

VERSION = "0.9.0"
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
    production_type: str = "short",
) -> dict[str, Any]:
    """Create a new Kitsu project (production) for a job.

    Each vref produce-start creates its own project so it appears
    as a separate production in the Kitsu UI.
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

    # Associate VideoRef entity type
    entity_types = await _kitsu_api(session, "GET", "/data/entity-types")
    vref_type = next(
        (t for t in entity_types if t["name"] == "VideoRef"), None
    )
    if vref_type:
        try:
            await _kitsu_api(
                session, "POST",
                f"/data/projects/{project['id']}/settings/asset-types",
                json_body={"asset_type_id": vref_type["id"]},
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
    """Post a comment on a task, setting status."""
    return await _kitsu_api(
        session, "POST",
        f"/actions/tasks/{task_id}/comment",
        json_body={"task_status_id": status_id, "text": text},
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
    """Send a Telegram notification. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


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

                # Pick first result that matches task type
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

                    # Skip video models for image tasks
                    if is_image_task and not is_video_task:
                        if any(v in node or v in name for v in [
                            "video", "kling", "veo", "seedance", "runway",
                            "sora", "luma", "minimax", "wan2", "animate",
                        ]):
                            continue

                    # Skip image models for video tasks
                    if is_video_task and not is_image_task:
                        if not any(v in node or v in name for v in [
                            "video", "kling", "veo", "seedance", "runway",
                            "sora", "luma", "minimax", "wan2", "animate",
                        ]):
                            continue

                    return p  # First matching result (highest similarity)

                # Fallback: return first result regardless
                return results[0]["payload"] if results else None
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

    Handles fal.ai nodes (simple prompt-based) and local nodes (full graph).
    """
    node_name = model.get("node", "")

    # fal.ai nodes are simple: just prompt + params
    if node_name.endswith("_fal"):
        workflow = {"prompt": {}}

        # Inject camera tokens into prompt
        full_prompt = _inject_camera_tokens(prompt, camera, lens)
        if style:
            full_prompt = f"{full_prompt}, {style}"

        # Common inputs for fal.ai nodes
        inputs: dict[str, Any] = {"prompt": full_prompt}

        # Add model-specific params
        tasks = model.get("tasks", [])
        if any(t in tasks for t in ["txt2vid", "img2vid", "video_production",
                                     "video_cinematic", "video_preview"]):
            inputs["duration"] = str(duration)
            inputs["aspect_ratio"] = f"{width}:{height}" if width > height else f"{height}:{width}"
            if reference_image:
                inputs["image"] = reference_image
        else:
            # Image gen — only add size params if the node accepts them
            # NanoBanana only takes prompt (+ optional aspect_ratio)
            node_lower = node_name.lower()
            if "nanobanana" in node_lower or "gpt" in node_lower:
                # These nodes auto-size, just pass aspect_ratio if available
                if width != height:
                    inputs["aspect_ratio"] = "16:9" if width > height else "9:16"
            elif "image_size" in str(model):
                inputs["image_size"] = f"{width}x{height}"
            else:
                inputs["width"] = width
                inputs["height"] = height
            if negative:
                inputs["negative_prompt"] = negative
            if reference_image:
                inputs["image"] = reference_image

        workflow["prompt"]["1"] = {
            "class_type": node_name,
            "inputs": inputs,
        }

        # fal.ai image nodes (ComfyUI-fal-API) return IMAGE tensors directly
        # Chain to SaveImage for local file output
        if "video" not in node_name.lower():
            workflow["prompt"]["2"] = {
                "class_type": "SaveImage",
                "inputs": {"images": ["1", 0], "filename_prefix": "composer"},
            }
        else:
            workflow["prompt"]["2"] = {
                "class_type": "SaveImage",
                "inputs": {"images": ["1", 0], "filename_prefix": "composer"},
            }

        workflow["_metadata"] = {
            "composer": True,
            "model": model.get("name", node_name),
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


async def _composer_submit(
    workflow: dict[str, Any], wait: bool = True, timeout_s: int = 180,
) -> dict[str, Any]:
    """Submit a workflow to ComfyUI /prompt API, optionally wait for result.

    If wait=True, polls /history/{prompt_id} until the image is ready,
    then returns {"status": "completed", "prompt_id": ..., "images": [...]}.
    """
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
                    return {"error": f"ComfyUI {resp.status}: {body[:200]}"}
                data = await resp.json()
                prompt_id = data.get("prompt_id", "")

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
                            # Extract output images
                            images = []
                            for node_id, outputs in entry.get("outputs", {}).items():
                                for img in outputs.get("images", []):
                                    images.append({
                                        "filename": img.get("filename", ""),
                                        "subfolder": img.get("subfolder", ""),
                                        "type": img.get("type", "output"),
                                    })
                            return {
                                "status": "completed",
                                "prompt_id": prompt_id,
                                "images": images,
                            }
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
    prod_type = params.get("production_type", "short")

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

    return {"status": "ok", "description": description, "kitsu": kitsu_result}, extras


async def _step_research(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle research step: analyze URL or search Qdrant."""
    url = params.get("url", job.get("url", ""))
    extras: dict[str, Any] = {}
    research_result: dict[str, Any] = {}

    if url:
        # Use existing analysis pipeline on a video URL
        # (Assumes video is already downloaded to WATCH_DIR)
        filename = Path(url).name if "/" in url else url
        src = WATCH_DIR / filename
        if src.exists():
            research_result = await run_analysis(filename)
            extras["scene_analyses"] = research_result.get("scenes", [])
        else:
            research_result = {"note": f"File not in watch dir: {filename}"}
    else:
        # Search Qdrant for similar references
        query = params.get("query", job.get("title", ""))
        results = await _search_qdrant(query, limit=5)
        research_result = {"qdrant_results": results}

    kitsu_result = await _kitsu_step_task(
        job, "Recherche", "done",
        f"Research completed.\n{json.dumps(research_result, indent=2)[:2000]}",
    )

    # Generate mood board from REAL analysis (style, colors, mood from video ref)
    mood_preview_id = ""
    concept_id = job.get("concept_id", extras.get("concept_id", ""))
    project_id = job.get("kitsu_project_id", "")
    scenes = extras.get("scene_analyses", research_result.get("scenes", []))

    if concept_id and project_id and scenes and KITSU_URL:
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
                        async with aiohttp.ClientSession() as ks:
                            concept_tt = await _kitsu_get_task_type_id(ks, "Concept")
                            concept_task = await _kitsu_get_or_create_task(
                                ks, concept_id, concept_tt, project_id,
                            )
                            done_id = await _kitsu_get_done_status_id(ks)
                            comment = await _kitsu_post_comment(
                                ks, concept_task["id"], done_id,
                                f"Mood board from video ref — {ref_style}, {ref_mood}",
                            )
                            if comment and comment.get("id"):
                                mood_preview_id = await _kitsu_upload_preview(
                                    ks, concept_task["id"],
                                    comment["id"], mood_bytes,
                                ) or ""
        except Exception as mood_exc:
            mood_preview_id = f"error: {mood_exc}"

    kitsu_result["mood_preview_id"] = mood_preview_id

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
        })

    extras = {"scene_prompts": scene_prompts}

    # Post all prompts as Kitsu comment
    comment = "\n\n".join(
        f"Scene {p['scene_index']+1}:\n{p['enriched']}" for p in scene_prompts
    )
    kitsu_result = await _kitsu_step_task(
        job, "Script", "done", f"Script prompts:\n\n{comment[:3000]}",
    )

    return {
        "status": "ok",
        "scene_prompts": scene_prompts,
        "kitsu": kitsu_result,
    }, extras


async def _step_storyboard(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle storyboard step: generate low-res frames via Composer.

    Composer selects: NanoBanana2 (eco), FluxSchnell (balanced), or FluxPro (premium).
    Best practice 2026: storyboard = fast + cheap, iterate quickly.
    """
    scene_prompts = job.get("scene_prompts", [])
    budget = params.get("budget", "eco")  # Storyboard = eco by default
    results: list[dict[str, Any]] = []

    # Select best model for storyboard task
    model = await _composer_select_model("storyboard text-to-image fast cheap", budget)
    model_name = model["name"] if model else "fallback"

    # If no scene_prompts yet, use job description as single prompt
    if not scene_prompts:
        desc = job.get("description", job.get("title", ""))
        if desc:
            scene_prompts = [{"enriched": desc, "original": desc, "scene_index": 1}]

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

                    # Upload to Kitsu as preview on storyboard task
                    if KITSU_URL and KITSU_TOKEN:
                        try:
                            shot_id = job.get("kitsu_overview_shot_id", "")
                            project_id = job.get("kitsu_project_id", "")
                            if shot_id and project_id:
                                async with aiohttp.ClientSession() as ks:
                                    task_type_id = await _kitsu_get_task_type_id(ks, "Storyboard CF")
                                    task = await _kitsu_get_or_create_task(
                                        ks, shot_id, task_type_id, project_id,
                                    )
                                    wfa_id = await _kitsu_get_status_id(ks, "wfa")
                                    comment = await _kitsu_post_comment(
                                        ks, task["id"], wfa_id,
                                        f"Storyboard frame S{sp.get('scene_index',0)} — {model_name}\n{prompt[:200]}",
                                    )
                                    if comment and comment.get("id"):
                                        pid = await _kitsu_upload_preview(
                                            ks, task["id"], comment["id"], img_bytes,
                                        )
                                        scene_result["kitsu_preview_id"] = pid
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
    """
    scene_prompts = job.get("scene_prompts", [])
    budget = params.get("budget", "balanced")
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

    # Generate at model-optimal resolution (not target — upscale later)
    gen_w = min(target_w, 1344) if target_w > target_h else min(target_w, 768)
    gen_h = min(target_h, 768) if target_w > target_h else min(target_h, 1344)
    # Ensure multiple of 8
    gen_w = (gen_w // 8) * 8
    gen_h = (gen_h // 8) * 8

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
            submit_result = await _composer_submit(workflow)

            # Generate short asset name for Kitsu
            analysis = sp.get("analysis", {})
            asset_name = _generate_asset_name(analysis, job.get("title", ""))

            results.append({
                "scene": sp.get("scene_index", 0),
                "model": model_name,
                "asset_name": asset_name,
                "gen_resolution": f"{gen_w}x{gen_h}",
                "target_resolution": resolution,
                "needs_upscale": gen_w < target_w or gen_h < target_h,
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
    duration = int(params.get("duration", job.get("fps", "24") == "24" and 5 or 5))
    results: list[dict[str, Any]] = []

    # Parse resolution
    resolution = job.get("resolution", "1920x1080")
    try:
        target_w, target_h = [int(x) for x in resolution.split("x")]
    except (ValueError, AttributeError):
        target_w, target_h = 1920, 1080

    # Select best video model
    model = await _composer_select_model(
        "video generation production animated clip best value", budget,
    )
    model_name = model["name"] if model else "fallback"

    for sp in scene_prompts:
        prompt = sp.get("enriched", sp.get("original", ""))
        if not prompt:
            continue

        if model:
            workflow = await _composer_build_workflow(
                model, prompt,
                width=target_w, height=target_h,
                style=job.get("style", ""),
                camera=job.get("camera", ""),
                lens=job.get("lens", ""),
                fps=int(job.get("fps", 24)),
                duration=duration,
            )
            submit_result = await _composer_submit(workflow)
            results.append({
                "scene": sp.get("scene_index", 0),
                "model": model_name,
                "duration": duration,
                "result": submit_result,
            })
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
    kitsu_note = (
        f"Video: {len(results)} clips via {model_name}, "
        f"{duration}s each, ~${total_cost:.2f} total. "
        f"Awaiting validation."
    )
    kitsu_result = await _kitsu_step_task(
        job, "Video Gen", "wfa", kitsu_note, cost_usd=total_cost,
    )

    return {
        "status": "ok",
        "model_used": model_name,
        "budget": budget,
        "duration_per_clip": duration,
        "estimated_cost_usd": total_cost,
        "videogen_results": results,
        "kitsu": kitsu_result,
    }, {}


async def _step_montage(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle montage step: assemble video scenes via n8n → Remotion."""
    scene_prompts = job.get("scene_prompts", [])
    transitions = params.get("transitions", "cut")

    # Call n8n creative-pipeline with type=video-composition for Remotion
    note = "Montage pending — manual at re.ewutelo.cloud"
    if N8N_CREATIVE_PIPELINE_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    N8N_CREATIVE_PIPELINE_URL,
                    json={
                        "type": "video-composition",
                        "composition": "MultiScene",
                        "input_props": {
                            "scenes": [
                                sp.get("enriched", sp.get("original", ""))
                                for sp in scene_prompts
                            ],
                            "transitions": transitions,
                            "duration": len(scene_prompts) * 5,
                        },
                        "agent_id": "videoref-engine",
                        "output_name": f"{job['job_id'][:8]}-montage",
                    },
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        note = f"Montage assembled via Remotion: {result.get('render_id', '?')}"
                        kitsu_result = await _kitsu_step_task(
                            job, "Montage", "wfa", note,
                        )
                        return {
                            "status": "ok",
                            "render_id": result.get("render_id"),
                            "result_url": result.get("result_url"),
                            "kitsu": kitsu_result,
                        }, {}
                    else:
                        body = await resp.text()
                        note = f"Remotion returned {resp.status}: {body[:100]}"
        except Exception as exc:
            note = f"Remotion montage failed: {exc}. Manual montage at re.ewutelo.cloud"

    kitsu_result = await _kitsu_step_task(job, "Montage", "wfa", note)
    return {"status": "ok", "note": note, "kitsu": kitsu_result}, {}


async def _step_subtitles(
    job: dict[str, Any], params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Handle subtitles step: whisper.cpp local transcription."""
    skip = params.get("skip", False)
    if skip:
        kitsu_result = await _kitsu_step_task(job, "Sous-titres", "done", "Skipped by user")
        return {"status": "ok", "note": "Skipped", "kitsu": kitsu_result}, {}

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
