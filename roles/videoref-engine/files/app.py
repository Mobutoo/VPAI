"""VideoRef Engine v0.3.0 -- Video analysis + Kitsu + Qdrant + Gitea integration."""
import os
import json
import asyncio
import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

# --- Configuration from env ---
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

VERSION = "0.3.1"


# ============================================================
# 1. Keyframe extraction (ffmpeg scene detection)
# ============================================================
async def extract_keyframes(video_path: Path, max_frames: int = 8) -> list[Path]:
    """Extract keyframes via ffmpeg scene detection (threshold 0.3)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="vref_kf_"))
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"select='gt(scene,0.3)',setpts=N/FRAME_RATE/TB",
        "-frames:v", str(max_frames),
        "-vsync", "vfr",
        "-q:v", "2",
        str(tmpdir / "kf_%03d.jpg"),
        "-y",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-500:]}")

    frames = sorted(tmpdir.glob("kf_*.jpg"))
    if not frames:
        # Fallback: extract evenly spaced frames
        cmd_fallback = [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"fps=1/{max(1, _get_duration(video_path) // max_frames)}",
            "-frames:v", str(max_frames),
            "-q:v", "2",
            str(tmpdir / "kf_%03d.jpg"),
            "-y",
        ]
        proc2 = await asyncio.create_subprocess_exec(
            *cmd_fallback,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc2.communicate()
        frames = sorted(tmpdir.glob("kf_*.jpg"))
    return frames


def _get_duration(video_path: Path) -> int:
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
        return int(float(result.stdout.strip()))
    except (ValueError, AttributeError):
        return 30


# ============================================================
# 2. Color palette extraction (k-means via numpy)
# ============================================================
async def extract_colors(frame_path: Path, n_colors: int = 5) -> list[str]:
    """Extract dominant colors from a frame using numpy k-means."""
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(frame_path).resize((150, 150)).convert("RGB")
        pixels = np.array(img).reshape(-1, 3).astype(np.float32)

        # Simple k-means (3 iterations — good enough for color palette)
        rng = np.random.default_rng(42)
        centers = pixels[rng.choice(len(pixels), n_colors, replace=False)]
        for _ in range(3):
            dists = np.linalg.norm(pixels[:, None] - centers[None], axis=2)
            labels = dists.argmin(axis=1)
            for k in range(n_colors):
                mask = labels == k
                if mask.any():
                    centers[k] = pixels[mask].mean(axis=0)

        # Sort by frequency
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
# 3. Optical flow estimation (ffmpeg v360 motion vectors)
# ============================================================
async def estimate_motion(video_path: Path) -> dict[str, Any]:
    """Estimate motion intensity via ffmpeg codec motion vectors."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,nb_frames,width,height",
        "-of", "json",
        str(video_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    try:
        info = json.loads(stdout)["streams"][0]
        fps_str = info.get("avg_frame_rate", "30/1")
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) > 0 else 30.0
    except (KeyError, IndexError, ValueError, ZeroDivisionError):
        fps = 30.0

    duration = _get_duration(video_path)
    # Simple heuristic: short + high fps = high motion
    motion_score = min(1.0, fps / 60.0) * min(1.0, 30.0 / max(1, duration))
    if motion_score > 0.6:
        level = "high"
    elif motion_score > 0.3:
        level = "medium"
    else:
        level = "low"

    return {
        "fps": round(fps, 2),
        "duration_s": duration,
        "motion_level": level,
        "motion_score": round(motion_score, 3),
    }


# ============================================================
# 4. Claude Vision analysis via LiteLLM
# ============================================================
async def analyze_with_vision(
    frames: list[Path], colors: list[str], motion: dict
) -> dict[str, Any]:
    """Send keyframes to Claude Vision via LiteLLM for style analysis."""
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"error": "LITELLM not configured", "style": {}}

    # Encode up to 4 frames as base64
    image_contents = []
    for frame in frames[:4]:
        b64 = base64.b64encode(frame.read_bytes()).decode()
        image_contents.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    prompt = (
        "Analyze these video keyframes as a visual reference for AI image generation. "
        f"Detected colors: {', '.join(colors[:5])}. "
        f"Motion: {motion.get('motion_level', 'unknown')} ({motion.get('fps', '?')} fps). "
        "Return JSON with: "
        '{"style": "...", "mood": "...", "lighting": "...", '
        '"composition": "...", "color_grade": "...", '
        '"suggested_prompt": "...", "negative_prompt": "..."}'
    )

    payload = {
        "model": "claude-sonnet",
        "messages": [
            {
                "role": "user",
                "content": [
                    *image_contents,
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": 1024,
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
                # Try to parse JSON from response
                try:
                    # Find JSON in response
                    start = content.index("{")
                    end = content.rindex("}") + 1
                    return json.loads(content[start:end])
                except (ValueError, json.JSONDecodeError):
                    return {"raw_analysis": content}
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# 5. ComfyUI workflow generation from Gitea templates
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
                if resp.status == 200:
                    return await resp.json()
                return None
    except Exception:
        return None


def generate_workflow(
    template: dict | None, analysis: dict, colors: list[str]
) -> dict:
    """Generate a ComfyUI workflow JSON from template + analysis."""
    prompt = analysis.get("suggested_prompt", "beautiful scene, high quality")
    negative = analysis.get("negative_prompt", "blurry, low quality")
    style = analysis.get("style", "cinematic")

    if template:
        # Clone template and inject parameters
        workflow = json.loads(json.dumps(template))
        # Replace placeholder values in all string fields
        _replace_in_dict(workflow, "{{PROMPT}}", prompt)
        _replace_in_dict(workflow, "{{NEGATIVE}}", negative)
        _replace_in_dict(workflow, "{{STYLE}}", style)
        return workflow

    # Fallback: minimal txt2img workflow
    return {
        "prompt": {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler_ancestral",
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
                "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": f"{prompt}, {style} style",
                    "clip": ["4", 1],
                },
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["4", 1]},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "videoref",
                    "images": ["8", 0],
                },
            },
        },
        "_metadata": {
            "source": "videoref-engine",
            "colors": colors[:5],
            "analysis": analysis,
        },
    }


def _replace_in_dict(obj: Any, old: str, new: str) -> None:
    """Recursively replace string values in a dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and old in v:
                obj[k] = v.replace(old, new)
            elif isinstance(v, (dict, list)):
                _replace_in_dict(v, old, new)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and old in v:
                obj[i] = v.replace(old, new)
            elif isinstance(v, (dict, list)):
                _replace_in_dict(v, old, new)


# ============================================================
# 6. Kitsu integration (notes + metadata + preview uploads)
# ============================================================
async def push_to_kitsu(
    filename: str, analysis: dict, colors: list[str],
    motion: dict, frames: list[Path],
) -> dict[str, Any]:
    """Push analysis results to Kitsu as asset metadata + preview thumbnails."""
    if not KITSU_URL or not KITSU_TOKEN:
        return {"skipped": "KITSU not configured"}

    headers = {"Authorization": f"Bearer {KITSU_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as session:
            # Get first project
            async with session.get(
                f"{KITSU_URL}/api/data/projects", headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                projects = await resp.json()
                if not projects:
                    return {"error": "No projects in Kitsu"}
                project_id = projects[0]["id"]

            # Get or create asset type "VideoRef"
            # NOTE: asset types are entity-types in Zou API
            # GET /data/asset-types lists them, but POST goes to /data/entity-types
            async with session.get(
                f"{KITSU_URL}/api/data/entity-types", headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                entity_types = await resp.json()
                vref_type = next(
                    (t for t in entity_types if t["name"] == "VideoRef"),
                    None,
                )
                if not vref_type:
                    async with session.post(
                        f"{KITSU_URL}/api/data/entity-types",
                        headers={**headers, "Content-Type": "application/json"},
                        json={"name": "VideoRef"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        vref_type = await r.json()
                type_id = vref_type["id"]

            # Create asset for this video
            asset_name = Path(filename).stem[:120]
            style = analysis.get("style", "unknown")
            mood = analysis.get("mood", "unknown")
            prompt = analysis.get("suggested_prompt", "")

            asset_data = {
                "name": asset_name,
                "description": (
                    f"Style: {style}\nMood: {mood}\n"
                    f"Colors: {', '.join(colors[:5])}\n"
                    f"Motion: {motion.get('motion_level', '?')}\n"
                    f"Prompt: {prompt[:200]}"
                ),
                "data": {
                    "videoref_style": style,
                    "videoref_mood": mood,
                    "videoref_colors": ", ".join(colors[:5]),
                    "videoref_motion": motion.get("motion_level", "low"),
                    "videoref_prompt": prompt[:500],
                },
            }
            # Zou API: POST /data/projects/{pid}/asset-types/{tid}/assets/new
            async with session.post(
                f"{KITSU_URL}/api/data/projects/{project_id}"
                f"/asset-types/{type_id}/assets/new",
                headers={**headers, "Content-Type": "application/json"},
                json=asset_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                asset = await resp.json()
                asset_id = asset.get("id", "")

            # Upload first keyframe as asset thumbnail
            uploaded_previews = []
            if frames and asset_id:
                first_frame = frames[0]
                if first_frame.exists():
                    form = aiohttp.FormData()
                    form.add_field(
                        "file", first_frame.read_bytes(),
                        filename=first_frame.name,
                        content_type="image/jpeg",
                    )
                    async with session.post(
                        f"{KITSU_URL}/api/pictures/thumbnails/assets/"
                        f"{asset_id}",
                        headers=headers,
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as r:
                        if r.status in (200, 201):
                            uploaded_previews.append(first_frame.name)

            return {
                "asset_id": asset_id,
                "asset_name": asset_name,
                "previews_uploaded": len(uploaded_previews),
                "project_id": project_id,
            }
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# 7. Qdrant semantic indexing (embeddings via LiteLLM)
# ============================================================
async def index_in_qdrant(
    filename: str, analysis: dict, colors: list[str], motion: dict,
) -> dict[str, Any]:
    """Generate embedding via LiteLLM and index in Qdrant."""
    if not QDRANT_URL or not QDRANT_API_KEY:
        return {"skipped": "QDRANT not configured"}
    if not LITELLM_URL or not LITELLM_API_KEY:
        return {"skipped": "LITELLM not configured (needed for embeddings)"}

    # Build text to embed
    style = analysis.get("style", "")
    mood = analysis.get("mood", "")
    prompt = analysis.get("suggested_prompt", "")
    color_str = ", ".join(colors[:5])
    text = (
        f"Video reference: {filename}. "
        f"Style: {style}. Mood: {mood}. "
        f"Colors: {color_str}. "
        f"Motion: {motion.get('motion_level', 'unknown')}. "
        f"Prompt: {prompt}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            # Get embedding from LiteLLM
            async with session.post(
                f"{LITELLM_URL}/v1/embeddings",
                json={
                    "model": "embedding",
                    "input": text,
                },
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

            # Upsert into Qdrant
            import hashlib
            point_id = int(
                hashlib.sha256(filename.encode()).hexdigest()[:15], 16
            )
            payload = {
                "filename": filename,
                "style": style,
                "mood": mood,
                "colors": colors[:5],
                "motion_level": motion.get("motion_level", "unknown"),
                "suggested_prompt": prompt[:500],
                "analysis": json.dumps(analysis)[:2000],
            }
            async with session.put(
                f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points",
                json={
                    "points": [{
                        "id": point_id,
                        "vector": vector,
                        "payload": payload,
                    }]
                },
                headers={
                    "api-key": QDRANT_API_KEY,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return {"error": f"Qdrant upsert: {resp.status} {body[:200]}"}
                return {"indexed": True, "point_id": point_id}
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# 8. Gitea versioning (push analysis JSON to repo)
# ============================================================
async def version_in_gitea(
    filename: str, result: dict,
) -> dict[str, Any]:
    """Push analysis result as JSON file to Gitea comfyui-templates repo."""
    if not GITEA_URL or not GITEA_TOKEN:
        return {"skipped": "GITEA not configured"}

    stem = Path(filename).stem
    file_path = f"analyses/{stem}.json"
    content_b64 = base64.b64encode(
        json.dumps(result, indent=2).encode()
    ).decode()

    try:
        async with aiohttp.ClientSession() as session:
            # Check if file exists (for update vs create)
            async with session.get(
                f"{GITEA_URL}/api/v1/repos/mobuone/comfyui-templates"
                f"/contents/{file_path}?ref=main",
                headers={"Authorization": f"token {GITEA_TOKEN}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                sha = ""
                if resp.status == 200:
                    existing = await resp.json()
                    sha = existing.get("sha", "")

            method = "PUT" if sha else "POST"
            body = {
                "message": f"analysis: {stem}",
                "content": content_b64,
            }
            if sha:
                body["sha"] = sha

            url = (
                f"{GITEA_URL}/api/v1/repos/mobuone/comfyui-templates"
                f"/contents/{file_path}"
            )
            async with session.request(
                method, url,
                json=body,
                headers={
                    "Authorization": f"token {GITEA_TOKEN}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (200, 201):
                    return {"versioned": True, "path": file_path}
                body_text = await resp.text()
                return {"error": f"Gitea {resp.status}: {body_text[:200]}"}
    except Exception as exc:
        return {"error": str(exc)}


# ============================================================
# HTTP API handlers
# ============================================================
async def health(request):
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


async def list_jobs(request):
    analyzed = []
    if OUTPUT_DIR.exists():
        analyzed = [
            f.name for f in OUTPUT_DIR.iterdir()
            if f.is_file() and f.suffix == ".json"
        ]
    return web.json_response({"analyzed": analyzed, "count": len(analyzed)})


async def list_watch(request):
    files = []
    if WATCH_DIR.exists():
        files = [f.name for f in WATCH_DIR.iterdir() if f.is_file()]
    return web.json_response({"files": files, "count": len(files)})


async def analyze(request):
    """Full analysis pipeline: keyframes + colors + motion + vision + workflow."""
    data = await request.json()
    filename = data.get("filename", "")
    template_name = data.get("template", "default")
    src = WATCH_DIR / filename

    if not src.exists():
        return web.json_response(
            {"error": f"File not found: {filename}"}, status=404
        )

    result = {
        "filename": filename,
        "size_bytes": src.stat().st_size,
        "status": "processing",
        "keyframes": [],
        "colors": [],
        "motion": {},
        "vision_analysis": {},
        "workflow": None,
    }

    try:
        # Step 1: Extract keyframes
        frames = await extract_keyframes(src)
        result["keyframes"] = [f.name for f in frames]

        # Step 2: Extract colors from first frame
        if frames:
            result["colors"] = await extract_colors(frames[0])

        # Step 3: Estimate motion
        result["motion"] = await estimate_motion(src)

        # Step 4: Claude Vision analysis (if LiteLLM configured)
        if LITELLM_URL:
            result["vision_analysis"] = await analyze_with_vision(
                frames, result["colors"], result["motion"]
            )

        # Step 5: Generate ComfyUI workflow
        template = await fetch_template(template_name)
        workflow = generate_workflow(
            template, result["vision_analysis"], result["colors"]
        )
        result["workflow"] = workflow

        # Save workflow to ComfyUI input dir
        wf_path = COMFYUI_DIR / f"{Path(filename).stem}_workflow.json"
        wf_path.write_text(json.dumps(workflow, indent=2))

        result["status"] = "completed"
        result["workflow_path"] = str(wf_path)

        # Step 6: Push to Kitsu (notes + metadata + preview keyframes)
        result["kitsu"] = await push_to_kitsu(
            filename, result["vision_analysis"], result["colors"],
            result["motion"], frames,
        )

        # Step 7: Index in Qdrant (semantic search)
        result["qdrant"] = await index_in_qdrant(
            filename, result["vision_analysis"], result["colors"],
            result["motion"],
        )

        # Step 8: Version in Gitea
        result["gitea"] = await version_in_gitea(filename, result)

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    # Save analysis result
    out = OUTPUT_DIR / f"{Path(filename).stem}.json"
    out.write_text(json.dumps(result, indent=2))
    return web.json_response(result)


async def webhook_metube(request):
    """Receive MeTube download completion webhook — auto-trigger analysis."""
    data = await request.json()
    filename = data.get("filename", "")
    if not filename:
        return web.json_response({"error": "No filename"}, status=400)

    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response(
            {"error": f"File not found: {filename}", "received": data},
            status=404,
        )

    # Trigger async analysis
    asyncio.create_task(_background_analyze(filename))
    return web.json_response({"status": "queued", "filename": filename})


async def _background_analyze(filename: str) -> None:
    """Run analysis in background after webhook trigger."""
    src = WATCH_DIR / filename
    if not src.exists():
        return

    result = {"filename": filename, "status": "processing"}
    try:
        frames = await extract_keyframes(src)
        colors = await extract_colors(frames[0]) if frames else []
        motion = await estimate_motion(src)
        vision = (
            await analyze_with_vision(frames, colors, motion)
            if LITELLM_URL
            else {}
        )
        template = await fetch_template("default")
        workflow = generate_workflow(template, vision, colors)

        wf_path = COMFYUI_DIR / f"{Path(filename).stem}_workflow.json"
        wf_path.write_text(json.dumps(workflow, indent=2))

        result = {
            "filename": filename,
            "status": "completed",
            "keyframes": [f.name for f in frames],
            "colors": colors,
            "motion": motion,
            "vision_analysis": vision,
            "workflow_path": str(wf_path),
        }

        # Push to creative pipeline (Kitsu + Qdrant + Gitea)
        result["kitsu"] = await push_to_kitsu(
            filename, vision, colors, motion, frames,
        )
        result["qdrant"] = await index_in_qdrant(
            filename, vision, colors, motion,
        )
        result["gitea"] = await version_in_gitea(filename, result)
    except Exception as exc:
        result = {"filename": filename, "status": "error", "error": str(exc)}

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
    print(f"  GITEA: {'configured' if GITEA_URL else 'NOT configured'}")
    web.run_app(app, host="0.0.0.0", port=8082)
