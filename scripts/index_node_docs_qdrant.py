#!/usr/bin/env python3
"""Index ComfyUI fal-API node documentation into Qdrant for agent lookups."""
import asyncio
import aiohttp
import os
import json
import hashlib

QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
LITELLM_URL = os.environ["LITELLM_URL"]
LITELLM_API_KEY = os.environ["LITELLM_API_KEY"]

COLLECTION = "comfyui-node-docs"

NODE_DOCS = [
    # IMAGE NODES
    {"node": "NanoBananaTextToImage_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, aspect_ratio (21:9|1:1|16:9|9:16|etc)", "size_control": "aspect_ratio only",
     "description": "NanoBanana 2 (Gemini Flash) text-to-image. Fast eco model. No width/height."},
    {"node": "NanoBananaPro_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, aspect_ratio, resolution (1K|2K|4K), images (optional edit)",
     "size_control": "aspect_ratio + resolution",
     "description": "NanoBanana Pro (Gemini 3 Pro). Higher quality. Auto-routes t2i vs edit."},
    {"node": "Imagen4Preview_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt ONLY", "size_control": "none",
     "description": "Google Imagen 4 Preview. Prompt only, zero options."},
    {"node": "FluxSchnell_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, image_size (preset), width, height, num_inference_steps (default 4)",
     "size_control": "image_size preset or custom w/h",
     "description": "Flux Schnell. Fast 4-step generation."},
    {"node": "FluxUltra_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, aspect_ratio", "size_control": "aspect_ratio only",
     "description": "Flux Pro Ultra. Premium quality. num_images capped at 1."},
    {"node": "GPTImage15_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, image_size (1024x1024|1536x1024|1024x1536), quality (low|medium|high)",
     "size_control": "image_size as WxH strings",
     "description": "GPT Image 1.5 (OpenAI). Fixed resolution options."},
    {"node": "Recraft_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, image_size (preset), width, height, style (24 options)",
     "size_control": "image_size preset or custom w/h",
     "description": "Recraft V3. 24 style presets including realistic, illustration, vector."},
    {"node": "Hidreamfull_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, image_size (preset), width, height",
     "size_control": "image_size preset or custom w/h",
     "description": "HiDream Full. Artistic image generation."},
    {"node": "Dreamina31TextToImage_fal", "type": "image", "returns": "IMAGE",
     "params": "prompt, image_size (preset only)", "size_control": "image_size presets only, NO custom w/h",
     "description": "ByteDance Dreamina 3.1. Presets only, no custom dimensions."},
    # VIDEO NODES
    {"node": "SeedanceTextToVideo_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, aspect_ratio, resolution (480p|720p), duration (5|10), camera_fixed",
     "size_control": "aspect_ratio + resolution",
     "description": "Seedance 2.0 txt2vid. Eco budget $0.10. Good creative control."},
    {"node": "SeedanceImageToVideo_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, image (required), resolution (480p|720p), duration (5|10), camera_fixed",
     "size_control": "resolution only (aspect from image)",
     "description": "Seedance 2.0 img2vid. Eco. Camera control."},
    {"node": "Kling25TurboPro_fal", "type": "video", "returns": "STRING (URL list)",
     "params": "prompt, image (required), duration (5|10), negative_prompt, cfg_scale",
     "size_control": "none",
     "description": "Kling 2.5 Turbo Pro i2v. No aspect_ratio param. Needs input image."},
    {"node": "Kling26Pro_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, duration (5|10), aspect_ratio (t2v only), image (optional), generate_audio",
     "size_control": "aspect_ratio (text-to-video only, NOT img2vid)",
     "description": "Kling 2.6 Pro. Dual mode t2v/i2v. Aspect only in t2v."},
    {"node": "KlingMaster_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, duration (5|10), aspect_ratio, image (optional)",
     "size_control": "aspect_ratio",
     "description": "Kling Master 3.0. Best value balanced. t2v and i2v."},
    {"node": "Veo3_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, aspect_ratio, duration FIXED 8s, generate_audio",
     "size_control": "aspect_ratio",
     "description": "Veo 3. Premium. Text-to-video ONLY. Fixed 8s duration. Native audio."},
    {"node": "Veo31_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, first_frame (IMAGE, required NOT 'image'), duration (4s|6s|8s), aspect_ratio, resolution, generate_audio",
     "size_control": "aspect_ratio + resolution",
     "description": "Veo 3.1. Premium i2v. IMPORTANT: image param is 'first_frame' not 'image'."},
    {"node": "Veo31Fast_fal", "type": "video", "returns": "STRING (URL)",
     "params": "same as Veo31_fal (first_frame, duration 4s|6s|8s)",
     "size_control": "aspect_ratio + resolution",
     "description": "Veo 3.1 Fast. Balanced i2v. Same params as Veo31_fal."},
    {"node": "Sora2Pro_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, image (required), duration (4|8|12 INTEGER not string!), resolution, aspect_ratio",
     "size_control": "aspect_ratio + resolution",
     "description": "Sora 2 Pro i2v. IMPORTANT: duration is INTEGER (4,8,12), not string."},
    {"node": "Wan26_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, duration (5|10|15), aspect_ratio (t2v only), resolution, image (optional)",
     "size_control": "aspect_ratio + resolution",
     "description": "WAN 2.6. Supports 15s! Dual t2v/i2v."},
    {"node": "LumaDreamMachine_fal", "type": "video", "returns": "STRING (URL)",
     "params": "prompt, mode (text-to-video|image-to-video), aspect_ratio, image (optional)",
     "size_control": "aspect_ratio",
     "description": "Luma Dream Machine Ray-2. No duration control."},
]


async def main():
    h_q = {"api-key": QDRANT_API_KEY, "Content-Type": "application/json"}
    h_l = {"Authorization": f"Bearer {LITELLM_API_KEY}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as s:
        # Create collection if not exists
        async with s.get(f"{QDRANT_URL}/collections/{COLLECTION}", headers=h_q) as r:
            if r.status != 200:
                # Get embedding dimension
                emb_r = await s.post(f"{LITELLM_URL}/v1/embeddings", headers=h_l,
                                     json={"model": "embedding", "input": "test"})
                emb = await emb_r.json()
                dim = len(emb["data"][0]["embedding"])
                await s.put(f"{QDRANT_URL}/collections/{COLLECTION}", headers=h_q,
                           json={"vectors": {"size": dim, "distance": "Cosine"}})
                print(f"Created collection {COLLECTION} (dim={dim})")
            else:
                print(f"Collection {COLLECTION} exists")

        # Index each node doc
        points = []
        for i, doc in enumerate(NODE_DOCS):
            # Build text for embedding
            text = f"{doc['node']} {doc['type']} {doc['description']} params: {doc['params']} size: {doc['size_control']}"
            emb_r = await s.post(f"{LITELLM_URL}/v1/embeddings", headers=h_l,
                                 json={"model": "embedding", "input": text})
            emb = await emb_r.json()
            vector = emb["data"][0]["embedding"]

            point_id = int(hashlib.md5(doc["node"].encode()).hexdigest()[:8], 16)
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": doc,
            })
            print(f"  [{i+1}/{len(NODE_DOCS)}] {doc['node']}")

        # Upsert all points
        async with s.put(f"{QDRANT_URL}/collections/{COLLECTION}/points", headers=h_q,
                        json={"points": points}) as r:
            result = await r.json()
            print(f"\nUpserted {len(points)} docs: {result.get('status', '?')}")


asyncio.run(main())
