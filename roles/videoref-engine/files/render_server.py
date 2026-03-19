"""Ephemeral Render Server — Chatterbox TTS + ACE-Step Music.

Runs on Hetzner CCX33 (8 CPU dédié, 32GB RAM, €0.07/h).
Spawned on-demand, auto-destroys after 30min idle.
"""
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from aiohttp import web

VERSION = "1.0.0"
OUTPUT_DIR = Path("/renders")
IDLE_TTL = int(os.environ.get("IDLE_TTL", "1800"))  # 30min default
_last_activity = time.time()

# Lazy-loaded models (heavy — load on first use)
_chatterbox_model = None
_acestep_pipeline = None


def _touch_activity():
    global _last_activity
    _last_activity = time.time()


# ── Chatterbox TTS ─────────────────────────────────────────

def _get_chatterbox():
    global _chatterbox_model
    if _chatterbox_model is None:
        print("[chatterbox] Loading model (first use)...")
        from chatterbox.tts import ChatterboxTTS
        _chatterbox_model = ChatterboxTTS.from_pretrained(device="cpu")
        print("[chatterbox] Model loaded")
    return _chatterbox_model


async def tts_generate(request: web.Request) -> web.Response:
    """POST /tts — Generate speech from text.

    Body: {"text": "...", "voice_ref": "url or base64", "language": "en"}
    Returns: audio file URL
    """
    _touch_activity()
    data = await request.json()
    text = data.get("text", "")
    voice_ref = data.get("voice_ref")
    output_name = data.get("output_name", f"tts-{int(time.time())}")

    if not text:
        return web.json_response({"error": "text required"}, status=400)

    try:
        model = _get_chatterbox()

        # Generate speech
        if voice_ref:
            # Voice cloning from reference audio
            import urllib.request
            ref_path = Path(tempfile.mktemp(suffix=".wav"))
            if voice_ref.startswith("http"):
                urllib.request.urlretrieve(voice_ref, str(ref_path))
            else:
                import base64
                ref_path.write_bytes(base64.b64decode(voice_ref))
            wav = model.generate(text, audio_prompt_path=str(ref_path))
        else:
            wav = model.generate(text)

        # Save output
        import soundfile as sf
        out_path = OUTPUT_DIR / f"{output_name}.wav"
        sf.write(str(out_path), wav.squeeze().numpy(), 24000)

        return web.json_response({
            "status": "ok",
            "output_path": str(out_path),
            "output_name": output_name,
            "duration_s": len(wav.squeeze()) / 24000,
        })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


# ── ACE-Step Music ─────────────────────────────────────────

def _get_acestep():
    global _acestep_pipeline
    if _acestep_pipeline is None:
        print("[ace-step] Loading model (first use, ~8GB)...")
        from ace_step import ACEStepPipeline
        _acestep_pipeline = ACEStepPipeline.from_pretrained(
            cpu_offload=True,
        )
        print("[ace-step] Model loaded")
    return _acestep_pipeline


async def music_generate(request: web.Request) -> web.Response:
    """POST /music — Generate music from text prompt.

    Body: {"prompt": "nostalgic piano...", "duration": 120, "output_name": "..."}
    Returns: audio file URL
    """
    _touch_activity()
    data = await request.json()
    prompt = data.get("prompt", "")
    duration = data.get("duration", 60)
    output_name = data.get("output_name", f"music-{int(time.time())}")

    if not prompt:
        return web.json_response({"error": "prompt required"}, status=400)

    try:
        pipeline = _get_acestep()

        # Generate music
        result = pipeline(
            prompt=prompt,
            duration=min(duration, 240),  # Cap at 4 min
        )

        # Save output
        import soundfile as sf
        out_path = OUTPUT_DIR / f"{output_name}.wav"
        sf.write(str(out_path), result["audio"], result["sample_rate"])

        return web.json_response({
            "status": "ok",
            "output_path": str(out_path),
            "output_name": output_name,
            "duration_s": duration,
            "sample_rate": result["sample_rate"],
        })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


# ── Lifecycle ──────────────────────────────────────────────

async def health(request: web.Request) -> web.Response:
    idle_s = int(time.time() - _last_activity)
    return web.json_response({
        "status": "ok",
        "version": VERSION,
        "idle_seconds": idle_s,
        "ttl_remaining": max(0, IDLE_TTL - idle_s),
        "chatterbox_loaded": _chatterbox_model is not None,
        "acestep_loaded": _acestep_pipeline is not None,
    })


async def shutdown(request: web.Request) -> web.Response:
    """POST /shutdown — Graceful shutdown (called after validation)."""
    return web.json_response({"status": "shutting_down"})


async def _idle_watchdog(app: web.Application) -> None:
    """Auto-shutdown after IDLE_TTL seconds of inactivity."""
    while True:
        await asyncio.sleep(60)
        idle = time.time() - _last_activity
        if idle > IDLE_TTL:
            print(f"[watchdog] Idle {int(idle)}s > TTL {IDLE_TTL}s — shutting down")
            # Signal the orchestrator to destroy this server
            try:
                import urllib.request
                callback = os.environ.get("DESTROY_CALLBACK_URL", "")
                if callback:
                    urllib.request.urlopen(callback, timeout=10)
            except Exception:
                pass
            # Exit the process — Docker will stop the container
            os._exit(0)


async def on_startup(app: web.Application) -> None:
    app["watchdog"] = asyncio.create_task(_idle_watchdog(app))


# ── App ────────────────────────────────────────────────────

app = web.Application()
app.router.add_get("/health", health)
app.router.add_post("/tts", tts_generate)
app.router.add_post("/music", music_generate)
app.router.add_post("/shutdown", shutdown)
app.on_startup.append(on_startup)

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Render Server {VERSION} starting...")
    print(f"  IDLE_TTL: {IDLE_TTL}s ({IDLE_TTL // 60}min)")
    print(f"  OUTPUT_DIR: {OUTPUT_DIR}")
    print(f"  Models: loaded on first use (lazy)")
    web.run_app(app, host="0.0.0.0", port=8090)
