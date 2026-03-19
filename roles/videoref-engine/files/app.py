"""VideoRef Engine v0.4.0 -- Multi-scene video analysis + Kitsu + Qdrant + Gitea."""
import os
import re
import json
import asyncio
import base64
import hashlib
import subprocess
import tempfile
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

VERSION = "0.5.0"
SCENE_THRESHOLD = 0.3
SHORT_VIDEO_SECONDS = 30


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


async def _kitsu_get_task_type_id(
    session: aiohttp.ClientSession, name: str = "Shot Analysis",
) -> str:
    """Get or create a task type by name. Returns its ID."""
    types = await _kitsu_api(session, "GET", "/data/task-types")
    existing = next((t for t in types if t["name"] == name), None)
    if existing:
        return existing["id"]
    created = await _kitsu_api(session, "POST", "/data/task-types", {"name": name})
    return created["id"]


async def _kitsu_get_done_status_id(session: aiohttp.ClientSession) -> str:
    """Get the 'Done' task status ID (by short_name='done')."""
    statuses = await _kitsu_api(session, "GET", "/data/task-status")
    done = next((s for s in statuses if s.get("short_name") == "done"), None)
    if done:
        return done["id"]
    raise RuntimeError("No 'done' task status found in Kitsu")


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
        body,
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
    try:
        return await _kitsu_api(
            session, "POST", "/data/tasks",
            {
                "entity_id": entity_id,
                "task_type_id": task_type_id,
                "project_id": project_id,
            },
        )
    except RuntimeError as e:
        if "already exists" in str(e).lower():
            # Race condition — retry fetch
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
    done_status_id: str,
    text: str,
) -> dict[str, Any]:
    """Post a comment on a task, setting status to Done."""
    return await _kitsu_api(
        session, "POST",
        f"/actions/tasks/{task_id}/comment",
        {"task_status_id": done_status_id, "text": text},
    )


async def _kitsu_upload_preview(
    session: aiohttp.ClientSession,
    task_id: str,
    comment_id: str,
    frame_path: Path,
) -> str | None:
    """Upload a keyframe as preview on a comment. Returns preview file ID."""
    # Step 1: create preview entry
    preview = await _kitsu_api(
        session, "POST",
        f"/actions/tasks/{task_id}/comments/{comment_id}/add-preview",
        {},
    )
    if not preview or "id" not in preview:
        return None
    preview_id = preview["id"]

    # Step 2: upload the file (POST, not PUT — Zou 1.0.21+)
    form = aiohttp.FormData()
    form.add_field(
        "file", frame_path.read_bytes(),
        filename=frame_path.name, content_type="image/jpeg",
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
            {},
        )
    except Exception:
        pass  # Non-critical if setting main preview fails

    return preview_id


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
            project = await _kitsu_get_project(session)
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
                    {"description": synthesis_text},
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
                {},
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
                style = analysis.get("style", "unknown")[:40]
                mood = analysis.get("mood", "unknown")[:30]
                asset_name = f"{seq_name[:50]} - S{idx+1:02d} {style}"
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
                        {
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
# HTTP API handlers
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
# App setup
# ============================================================
app = web.Application()
app.router.add_get("/health", health)
app.router.add_get("/api/jobs", list_jobs)
app.router.add_get("/api/watch", list_watch)
app.router.add_post("/api/analyze", analyze)
app.router.add_post("/api/webhook/metube", webhook_metube)

if __name__ == "__main__":
    for d in [OUTPUT_DIR, COMFYUI_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print(f"VideoRef Engine {VERSION} starting...")
    print(f"  WATCH_DIR: {WATCH_DIR}")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    print(f"  COMFYUI_DIR: {COMFYUI_DIR}")
    print(f"  LITELLM: {'configured' if LITELLM_URL else 'NOT configured'}")
    print(f"  KITSU: {'configured' if KITSU_URL else 'NOT configured'}")
    print(f"  QDRANT: {'configured' if QDRANT_URL else 'NOT configured'}")
    print(f"  GITEA: {'configured' if GITEA_URL else 'NOT configured'}")
    web.run_app(app, host="0.0.0.0", port=8082)
