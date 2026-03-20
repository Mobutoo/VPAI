#!/usr/bin/env python3
"""Index REX Session 17 (2026-03-20) into Qdrant operational-rex collection."""
import asyncio, aiohttp, os, json, hashlib

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
LITELLM_URL = os.environ["LITELLM_URL"]
LITELLM_API_KEY = os.environ["LITELLM_API_KEY"]
COLLECTION = "operational-rex"

REX_ENTRIES = [
    # === fal.ai Video Nodes ===
    {
        "title": "ComfyUI fal-API video nodes return STRING not IMAGE",
        "category": "fal.ai",
        "severity": "critical",
        "description": "All ComfyUI-fal-API video nodes (Seedance, Kling, Veo, etc.) return STRING (video URL), "
        "not IMAGE tensor. Chaining SaveImage after a video node causes 'prompt_outputs_failed_validation' or "
        "'prompt_no_outputs' errors. Solution: bypass ComfyUI entirely for video nodes, call fal.ai REST API "
        "directly via queue.fal.run.",
    },
    {
        "title": "fal.ai response_url is broken for some providers (MiniMax)",
        "category": "fal.ai",
        "severity": "high",
        "description": "fal.ai queue submit returns response_url like 'queue.fal.run/fal-ai/minimax/requests/{id}' "
        "but GET on this URL returns 404 'Path /video-01/text-to-video not found' for MiniMax provider. "
        "Seedance, Veo, Kling response_url works correctly. Solution: blacklist MiniMax nodes, use response_url "
        "as-is (don't append /response), use content_type=None for json parsing.",
    },
    {
        "title": "fal.ai duration parameter format varies per node",
        "category": "fal.ai",
        "severity": "medium",
        "description": "Duration format is inconsistent across fal.ai video nodes: "
        "Seedance/Kling/WAN: string '5','10'. Veo: string with suffix '4s','6s','8s'. "
        "Sora2Pro: integer 4,8,12. Veo31/Veo31Fast: image param is 'first_frame' not 'image'. "
        "Solution: _FAL_NODE_SPECS dict maps each node's exact params from source code.",
    },
    {
        "title": "fal.ai queue polling — use response_url from submit, not construct it",
        "category": "fal.ai",
        "severity": "high",
        "description": "fal.ai queue API: POST queue.fal.run/{endpoint} returns request_id, status_url, response_url. "
        "status_url works for polling. response_url works for fetching result (for most providers). "
        "Do NOT construct the result URL from endpoint+request_id — the routing prefix differs. "
        "Do NOT append /response to the URL. Use content_type=None when parsing JSON response.",
    },
    # === LiteLLM Budget ===
    {
        "title": "LiteLLM 429 is provider error, not always budget",
        "category": "litellm",
        "severity": "high",
        "description": "LiteLLM returns 429 in two cases: (1) global budget exceeded (max_budget in general_settings), "
        "(2) upstream provider rate limit (Google Gemini free tier quota). The error message contains the provider error. "
        "global/spend/reset API resets LiteLLM internal counter but NOT provider quotas. "
        "Solution: fallback to different provider (gpt-4o-mini works when gemini-flash is 429).",
    },
    {
        "title": "LiteLLM spend reset does not reset on container restart",
        "category": "litellm",
        "severity": "medium",
        "description": "Restarting LiteLLM container does NOT reset the daily spend counter — it's stored in "
        "PostgreSQL. To reset: POST /global/spend/reset with master key from INSIDE the container "
        "(docker exec javisi_litellm python3 -c 'import requests; requests.post(\"http://localhost:4000/global/spend/reset\", "
        "headers={\"Authorization\": \"Bearer sk-lm-...\"})'). Config max_budget change takes effect after restart.",
    },
    {
        "title": "LiteLLM model name must match config exactly",
        "category": "litellm",
        "severity": "medium",
        "description": "Model names in LiteLLM must exactly match what's configured in litellm_config.yaml. "
        "'fast' does not exist — use 'gemini-flash', 'gpt-4o-mini', 'claude-haiku', etc. "
        "Available models: claude-opus, claude-sonnet, claude-haiku, gpt-4o, gpt-4o-mini, gemini-flash, "
        "deepseek-v3, qwen3-coder, kimi-k2, grok-search, seedream.",
    },
    # === Pipeline Architecture ===
    {
        "title": "Pipeline scene_prompts empty causes silent videogen failure",
        "category": "videoref-pipeline",
        "severity": "critical",
        "description": "If _step_script() does not generate scene_prompts (scene_analyses empty or poor), "
        "videogen iterates over empty list and returns 0 videos without error. "
        "Root cause: _step_research() creates 1 synthetic scene when video file not in WATCH_DIR. "
        "Solution: (1) download MeTube video before analysis, (2) LLM scene decomposition fallback, "
        "(3) videogen failsafe builds prompt from job description.",
    },
    {
        "title": "LLM scene decomposition for text-only briefs",
        "category": "videoref-pipeline",
        "severity": "high",
        "description": "When no video reference, use LLM (gpt-4o-mini) to decompose brief into N structured scenes. "
        "Returns JSON array with scene_index, description, visual_prompt, camera_movement, mood, duration_seconds. "
        "num_scenes parameterizable via params['num_scenes'] (default 5). "
        "Implemented in _llm_decompose_scenes() with Gemini direct fallback when LiteLLM budget exceeded.",
    },
    {
        "title": "LLM entity extraction for Kitsu assets",
        "category": "videoref-pipeline",
        "severity": "medium",
        "description": "Use LLM to extract characters, environments, props from brief. "
        "Create Kitsu assets by entity type (not by scene). "
        "Cast all assets into all shots via breakdown/casting API. "
        "Implemented in _llm_extract_entities() → _kitsu_create_asset() per entity.",
    },
    # === Kitsu Integration ===
    {
        "title": "Kitsu production_type must be tvshow not short",
        "category": "kitsu",
        "severity": "critical",
        "description": "Kitsu production_type 'short' has bugs with assets/concepts in self-hosted Zou. "
        "Always use 'tvshow' — it supports all features: assets, shots, sequences, concepts, breakdown. "
        "Documented in app.py line 576. Validated by REX session 11.",
    },
    {
        "title": "Kitsu preview upload requires comment on task",
        "category": "kitsu",
        "severity": "high",
        "description": "Previews in Kitsu are attached to Comments on Tasks, not directly to entities. "
        "Flow: (1) get/create task on shot, (2) post comment with status change, (3) upload preview file "
        "on comment. Cannot upload preview without comment. WFA status triggers 'Publish Revision' tab in UI.",
    },
    {
        "title": "Kitsu concept preview upload method",
        "category": "kitsu",
        "severity": "medium",
        "description": "Concept entities in Kitsu accept direct preview upload via POST /pictures/concepts/{id}. "
        "Mood board generated by NanoBanana in _step_research() is uploaded as concept preview. "
        "Retry once on failure. Log success/failure for debugging.",
    },
    {
        "title": "Kitsu video preview upload fails with 502 on large files",
        "category": "kitsu",
        "severity": "high",
        "description": "Uploading MP4 videos (7-15MB) as preview files to Kitsu returns 502 Bad Gateway. "
        "Likely nginx proxy body size limit or Zou processing timeout. "
        "Storyboard images (1-2MB PNG) upload successfully. "
        "TODO: configure nginx client_max_body_size or use external URL reference.",
    },
    # === Docker Permissions ===
    {
        "title": "videoref container needs DAC_OVERRIDE and FOWNER capabilities",
        "category": "docker",
        "severity": "high",
        "description": "videoref-engine runs as root but cap_drop: ALL removes filesystem capabilities. "
        "Writing to /analyzed volume fails with Permission denied. "
        "Fix: add cap_add: CHOWN, DAC_OVERRIDE, FOWNER in docker-compose-creative.yml. "
        "Template has it but deployed file may not — verify after each compose redeploy.",
    },
    # === Telegram ===
    {
        "title": "Telegram video: send URL for streaming, not file upload",
        "category": "telegram",
        "severity": "medium",
        "description": "For video clips, use sendVideo with video=URL (Telegram fetches and streams) "
        "instead of uploading the file (50MB limit). JSON payload with message_thread_id as integer. "
        "For montage final (assembled video), upload the file directly if <50MB.",
    },
    {
        "title": "Telegram notifications go to OpenClaw bot topic 173 Studio",
        "category": "telegram",
        "severity": "medium",
        "description": "Creative pipeline notifications use TELEGRAM_BOT_TOKEN (OpenClaw bot), "
        "TELEGRAM_CHAT_ID (OpenClaw group), TELEGRAM_TOPIC_ID (173 = Studio topic). "
        "NOT the monitoring bot (Ekenge). Configured in videoref.env.j2.",
    },
    # === Qdrant ===
    {
        "title": "comfyui-node-docs collection for node parameter lookup",
        "category": "qdrant",
        "severity": "low",
        "description": "20 node specs indexed in Qdrant collection 'comfyui-node-docs'. "
        "Each doc has: node name, type (image/video), return type, params, size_control. "
        "Searchable by semantic query. Indexed via scripts/index_node_docs_qdrant.py.",
    },
    # === Montage / Remaining Work ===
    {
        "title": "Montage should use Remotion, not ffmpeg concat",
        "category": "videoref-pipeline",
        "severity": "high",
        "description": "Current montage step does basic ffmpeg -c copy concat. "
        "Should integrate with Remotion (re.ewutelo.cloud) for proper video composition "
        "with transitions, text overlays, timing. n8n webhook 'video-composition' exists "
        "but needs Remotion MultiScene composition to be configured. "
        "TODO: configure Remotion composition, wire n8n webhook, test E2E.",
    },
]


async def main():
    h_q = {"api-key": QDRANT_API_KEY, "Content-Type": "application/json"}
    h_l = {"Authorization": f"Bearer {LITELLM_API_KEY}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as s:
        # Verify collection exists
        async with s.get(f"{QDRANT_URL}/collections/{COLLECTION}", headers=h_q) as r:
            if r.status != 200:
                print(f"Collection {COLLECTION} not found!")
                return
            info = await r.json()
            count = info.get("result", {}).get("points_count", 0)
            print(f"Collection {COLLECTION}: {count} existing points")

        # Index each REX entry
        points = []
        for i, entry in enumerate(REX_ENTRIES):
            text = f"REX 2026-03-20 Session 17: {entry['title']}. {entry['description']}"
            emb_r = await s.post(
                f"{LITELLM_URL}/v1/embeddings", headers=h_l,
                json={"model": "embedding", "input": text},
            )
            emb = await emb_r.json()
            vector = emb["data"][0]["embedding"]

            point_id = int(hashlib.md5(entry["title"].encode()).hexdigest()[:8], 16)
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": {
                    "title": entry["title"],
                    "category": entry["category"],
                    "severity": entry["severity"],
                    "description": entry["description"],
                    "session": "2026-03-20-session-17",
                    "source": "REX-SESSION-2026-03-20",
                },
            })
            print(f"  [{i+1}/{len(REX_ENTRIES)}] {entry['title'][:60]}")

        # Upsert all points
        async with s.put(
            f"{QDRANT_URL}/collections/{COLLECTION}/points",
            headers=h_q, json={"points": points},
        ) as r:
            result = await r.json()
            print(f"\nUpserted {len(points)} REX entries: {result.get('status', '?')}")


asyncio.run(main())
