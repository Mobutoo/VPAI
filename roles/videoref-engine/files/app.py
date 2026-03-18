"""VideoRef Engine -- Minimal API for video reference analysis."""
import os
import json
import asyncio
from pathlib import Path
from aiohttp import web

WATCH_DIR = Path(os.environ.get("WATCH_DIR", "/watch"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/analyzed"))
COMFYUI_DIR = Path(os.environ.get("COMFYUI_WORKFLOWS_DIR", "/comfyui-workflows"))


async def health(request):
    return web.json_response({"status": "ok", "version": "0.1.0"})


async def list_jobs(request):
    analyzed = []
    if OUTPUT_DIR.exists():
        analyzed = [f.name for f in OUTPUT_DIR.iterdir() if f.is_file()]
    return web.json_response({"analyzed": analyzed, "count": len(analyzed)})


async def analyze(request):
    data = await request.json()
    filename = data.get("filename", "")
    src = WATCH_DIR / filename
    if not src.exists():
        return web.json_response(
            {"error": f"File not found: {filename}"}, status=404
        )

    result = {
        "filename": filename,
        "size_bytes": src.stat().st_size,
        "status": "analyzed",
        "keyframes": [],
        "colors": [],
        "workflow": None,
    }
    out = OUTPUT_DIR / f"{Path(filename).stem}.json"
    out.write_text(json.dumps(result, indent=2))
    return web.json_response(result)


async def list_watch(request):
    files = []
    if WATCH_DIR.exists():
        files = [f.name for f in WATCH_DIR.iterdir() if f.is_file()]
    return web.json_response({"files": files, "count": len(files)})


app = web.Application()
app.router.add_get("/health", health)
app.router.add_get("/api/jobs", list_jobs)
app.router.add_get("/api/watch", list_watch)
app.router.add_post("/api/analyze", analyze)

if __name__ == "__main__":
    for d in [OUTPUT_DIR, COMFYUI_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    web.run_app(app, host="0.0.0.0", port=8082)
