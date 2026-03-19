#!/usr/bin/env python3
"""Build the model-registry Qdrant collection from our ComfyUI nodes.

Indexes every available fal.ai, Gemini, and local model with:
- task types (storyboard, keyframe, video, upscale, inpaint, etc.)
- quality/speed/cost ratings
- required inputs
- ComfyUI node name
- budget tier (eco/balanced/premium)

This registry powers the Workflow Composer in VideoRef Engine.
"""
import hashlib
import json
import os
import time
import urllib.request

LITELLM_URL = os.environ.get("LITELLM_URL", "https://llm.ewutelo.cloud")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "")
QDRANT_URL = os.environ.get("QDRANT_URL", "https://qd.ewutelo.cloud")
QDRANT_KEY = os.environ.get("QDRANT_KEY", "")
COLLECTION = "model-registry"
VECTOR_SIZE = 1536

# === MODEL CATALOG ===
# Each model: node name, tasks, quality (1-10), speed, cost, budget tier, notes
MODELS = [
    # --- IMAGE: Storyboard (fast, cheap, text-friendly) ---
    {"node": "NanoBananaTextToImage_fal", "name": "NanoBanana 2 (Gemini Flash)",
     "tasks": ["storyboard", "txt2img", "concept_art"], "quality": 8, "speed": "fast",
     "cost": 0.0, "budget": "eco", "text_in_image": True, "max_resolution": "4K",
     "provider": "google", "notes": "Best for storyboards — free, fast, good text rendering"},
    {"node": "NanoBananaPro_fal", "name": "NanoBanana Pro (Gemini 3 Pro)",
     "tasks": ["keyframe", "storyboard", "txt2img", "4k"], "quality": 9, "speed": "medium",
     "cost": 0.0, "budget": "eco", "text_in_image": True, "max_resolution": "4K",
     "provider": "google", "notes": "4K native, studio controls, color grading"},
    {"node": "FluxSchnell_fal", "name": "Flux Schnell",
     "tasks": ["storyboard", "txt2img", "rapid_prototype"], "quality": 7, "speed": "very_fast",
     "cost": 0.003, "budget": "eco", "provider": "bfl",
     "notes": "Fastest Flux, good for rapid iteration"},
    {"node": "GPTImage15_fal", "name": "GPT Image 1.5 (OpenAI)",
     "tasks": ["storyboard", "txt2img", "edit"], "quality": 8, "speed": "medium",
     "cost": 0.02, "budget": "balanced", "text_in_image": True, "provider": "openai",
     "notes": "OpenAI image gen, good instruction following"},
    {"node": "Ideogramv3_fal", "name": "Ideogram v3",
     "tasks": ["storyboard", "txt2img", "typography", "logo"], "quality": 8, "speed": "medium",
     "cost": 0.04, "budget": "balanced", "text_in_image": True, "provider": "ideogram",
     "notes": "Best text-in-image rendering, great for titles/logos"},

    # --- IMAGE: Keyframe final (high quality) ---
    {"node": "FluxPro11_fal", "name": "Flux Pro 1.1",
     "tasks": ["keyframe", "final_render", "txt2img"], "quality": 10, "speed": "medium",
     "cost": 0.05, "budget": "premium", "provider": "bfl",
     "notes": "Highest quality Flux, production-grade"},
    {"node": "FluxUltra_fal", "name": "Flux Ultra",
     "tasks": ["keyframe", "final_render", "ultra_resolution"], "quality": 10, "speed": "slow",
     "cost": 0.06, "budget": "premium", "provider": "bfl",
     "notes": "Ultra-high resolution, best for hero shots"},
    {"node": "Hidreamfull_fal", "name": "HiDream Full",
     "tasks": ["keyframe", "txt2img", "artistic"], "quality": 9, "speed": "medium",
     "cost": 0.04, "budget": "balanced", "provider": "hidream",
     "notes": "Very detailed, artistic style"},
    {"node": "Recraft_fal", "name": "Recraft",
     "tasks": ["keyframe", "txt2img", "illustration", "vector"], "quality": 8, "speed": "medium",
     "cost": 0.04, "budget": "balanced", "provider": "recraft",
     "notes": "Design-oriented, great for illustrations"},
    {"node": "Dreamina31TextToImage_fal", "name": "Dreamina 3.1",
     "tasks": ["keyframe", "txt2img"], "quality": 8, "speed": "medium",
     "cost": 0.03, "budget": "balanced", "provider": "bytedance",
     "notes": "ByteDance image gen, good quality"},
    {"node": "ReveTextToImage_fal", "name": "Reve",
     "tasks": ["keyframe", "txt2img", "artistic"], "quality": 8, "speed": "medium",
     "cost": 0.03, "budget": "balanced", "provider": "reve"},
    {"node": "Imagen4Preview_fal", "name": "Imagen 4 (Google)",
     "tasks": ["keyframe", "txt2img"], "quality": 9, "speed": "medium",
     "cost": 0.04, "budget": "balanced", "provider": "google",
     "notes": "Google Imagen 4, photorealistic"},

    # --- IMAGE: Character consistency ---
    {"node": "FluxProKontext_fal", "name": "Flux Pro Kontext",
     "tasks": ["character_sheet", "character_consistency", "img2img"], "quality": 9, "speed": "medium",
     "cost": 0.05, "budget": "premium", "provider": "bfl",
     "notes": "Best for character consistency — input reference, get consistent output"},
    {"node": "FluxProKontextMulti_fal", "name": "Flux Pro Kontext Multi",
     "tasks": ["character_consistency", "multi_reference", "style_transfer"], "quality": 9,
     "speed": "slow", "cost": 0.06, "budget": "premium", "provider": "bfl",
     "notes": "Multi-image context for complex character/style transfer"},
    {"node": "FluxProKontextTextToImage_fal", "name": "Flux Pro Kontext Text2Img",
     "tasks": ["character_sheet", "txt2img"], "quality": 9, "speed": "medium",
     "cost": 0.05, "budget": "premium", "provider": "bfl"},
    {"node": "FluxLora_fal", "name": "Flux LoRA",
     "tasks": ["character_consistency", "style_transfer", "custom_model"], "quality": 9,
     "speed": "medium", "cost": 0.04, "budget": "balanced", "provider": "bfl",
     "notes": "Use with trained LoRA for perfect character consistency"},
    {"node": "IPAdapterFaceID", "name": "IPAdapter FaceID (local)",
     "tasks": ["character_consistency", "face_preservation"], "quality": 7, "speed": "slow",
     "cost": 0.0, "budget": "eco", "provider": "local",
     "notes": "Local face-driven generation, no API cost"},

    # --- IMAGE: Style transfer & editing ---
    {"node": "NanoBananaEdit_fal", "name": "NanoBanana Edit",
     "tasks": ["edit", "inpaint", "style_transfer"], "quality": 8, "speed": "fast",
     "cost": 0.0, "budget": "eco", "provider": "google",
     "notes": "Free edit/inpaint via Gemini"},
    {"node": "FluxPro1Fill_fal", "name": "Flux Pro Fill",
     "tasks": ["inpaint", "fill", "outpaint"], "quality": 10, "speed": "medium",
     "cost": 0.05, "budget": "premium", "provider": "bfl",
     "notes": "Best inpainting quality"},
    {"node": "SeedEditV3_fal", "name": "SeedEdit V3",
     "tasks": ["edit", "style_transfer"], "quality": 8, "speed": "medium",
     "cost": 0.03, "budget": "balanced", "provider": "bytedance"},
    {"node": "QwenImageEdit_fal", "name": "Qwen Image Edit",
     "tasks": ["edit", "txt_guided_edit"], "quality": 8, "speed": "medium",
     "cost": 0.03, "budget": "balanced", "provider": "alibaba"},
    {"node": "SeedreamV4Edit_fal", "name": "Seedream V4 Edit",
     "tasks": ["edit", "style_transfer"], "quality": 8, "speed": "medium",
     "cost": 0.03, "budget": "balanced", "provider": "bytedance"},

    # --- IMAGE: Upscale ---
    {"node": "Upscaler_fal", "name": "AI Upscaler (fal.ai)",
     "tasks": ["upscale", "enhance"], "quality": 9, "speed": "fast",
     "cost": 0.02, "budget": "balanced", "provider": "fal",
     "notes": "AI upscale with creativity control"},
    {"node": "Seedvr_Upscaler_fal", "name": "Seedvr Upscaler",
     "tasks": ["upscale"], "quality": 8, "speed": "fast",
     "cost": 0.02, "budget": "balanced", "provider": "bytedance"},
    {"node": "ImageUpscaleWithModel", "name": "RealESRGAN (local)",
     "tasks": ["upscale"], "quality": 7, "speed": "slow",
     "cost": 0.0, "budget": "eco", "provider": "local",
     "notes": "Free local upscale, needs model file"},

    # --- VIDEO: Preview (2-4s, fast) ---
    {"node": "Kling25TurboPro_fal", "name": "Kling 2.5 Turbo Pro",
     "tasks": ["video_preview", "txt2vid", "img2vid"], "quality": 8, "speed": "fast",
     "cost": 0.10, "budget": "balanced", "provider": "kuaishou",
     "notes": "Fastest video gen with good quality, ~4s clips"},
    {"node": "Wan25_preview_fal", "name": "WAN 2.5 Preview",
     "tasks": ["video_preview", "img2vid"], "quality": 7, "speed": "very_fast",
     "cost": 0.05, "budget": "eco", "provider": "alibaba",
     "notes": "Ultra-fast video preview"},
    {"node": "AnimateDiff", "name": "AnimateDiff (local)",
     "tasks": ["video_preview", "animation"], "quality": 6, "speed": "slow",
     "cost": 0.0, "budget": "eco", "provider": "local",
     "notes": "Free local animation, 16 frames, CPU-only on RPi5"},

    # --- VIDEO: Production (5-10s) ---
    {"node": "Kling26Pro_fal", "name": "Kling 2.6 Pro",
     "tasks": ["video_production", "txt2vid"], "quality": 9, "speed": "medium",
     "cost": 0.30, "budget": "balanced", "provider": "kuaishou",
     "notes": "Best motion quality for production clips"},
    {"node": "Veo31Fast_fal", "name": "Veo 3.1 Fast",
     "tasks": ["video_production", "txt2vid", "audio_native"], "quality": 9, "speed": "fast",
     "cost_per_sec": 0.15, "budget": "balanced", "provider": "google",
     "notes": "Veo 3.1 Fast — native audio, 720p-1080p"},
    {"node": "SeedanceTextToVideo_fal", "name": "Seedance Text2Video",
     "tasks": ["video_production", "txt2vid"], "quality": 8, "speed": "medium",
     "cost": 0.20, "budget": "balanced", "provider": "bytedance",
     "notes": "Seedance text-to-video with camera control"},
    {"node": "RunwayGen3_fal", "name": "Runway Gen-3",
     "tasks": ["video_production", "txt2vid", "img2vid"], "quality": 9, "speed": "medium",
     "cost": 0.25, "budget": "premium", "provider": "runway"},
    {"node": "KlingMaster_fal", "name": "Kling Master",
     "tasks": ["video_production", "txt2vid", "long_video"], "quality": 9, "speed": "slow",
     "cost": 0.40, "budget": "premium", "provider": "kuaishou",
     "notes": "Flexible duration, master quality"},
    {"node": "MiniMaxTextToVideo_fal", "name": "MiniMax Text2Video",
     "tasks": ["video_production", "txt2vid"], "quality": 8, "speed": "medium",
     "cost": 0.15, "budget": "balanced", "provider": "minimax"},
    {"node": "Wan26_fal", "name": "WAN 2.6",
     "tasks": ["video_production", "txt2vid"], "quality": 8, "speed": "medium",
     "cost": 0.15, "budget": "balanced", "provider": "alibaba"},

    # --- VIDEO: Premium cinematic ---
    {"node": "Veo3_fal", "name": "Veo 3",
     "tasks": ["video_cinematic", "txt2vid", "audio_native"], "quality": 10, "speed": "slow",
     "cost_per_sec": 0.75, "budget": "premium", "provider": "google",
     "notes": "Best video quality + native audio, 1080p"},
    {"node": "Veo31_fal", "name": "Veo 3.1 Standard",
     "tasks": ["video_cinematic", "txt2vid", "4k_video", "audio_native"], "quality": 10,
     "speed": "slow", "cost_per_sec": 0.40, "budget": "premium", "provider": "google",
     "notes": "4K video with native audio"},
    {"node": "Sora2Pro_fal", "name": "Sora 2 Pro",
     "tasks": ["video_cinematic", "txt2vid"], "quality": 10, "speed": "slow",
     "cost": 0.50, "budget": "premium", "provider": "openai",
     "notes": "OpenAI Sora 2, highest visual fidelity"},

    # --- VIDEO: Image to Video ---
    {"node": "KlingOmniImageToVideo_fal", "name": "Kling Omni i2v",
     "tasks": ["img2vid", "keyframe_to_clip"], "quality": 9, "speed": "medium",
     "cost": 0.20, "budget": "balanced", "provider": "kuaishou",
     "notes": "Best image-to-video, preserves source faithfully"},
    {"node": "Veo2ImageToVideo_fal", "name": "Veo 2 i2v",
     "tasks": ["img2vid", "keyframe_to_clip"], "quality": 9, "speed": "medium",
     "cost_per_sec": 0.30, "budget": "balanced", "provider": "google"},
    {"node": "SeedanceImageToVideo_fal", "name": "Seedance i2v",
     "tasks": ["img2vid", "keyframe_to_clip"], "quality": 8, "speed": "medium",
     "cost": 0.15, "budget": "balanced", "provider": "bytedance",
     "notes": "Camera control in i2v"},
    {"node": "LumaDreamMachine_fal", "name": "Luma Dream Machine",
     "tasks": ["img2vid", "txt2vid"], "quality": 8, "speed": "medium",
     "cost": 0.15, "budget": "balanced", "provider": "luma"},
    {"node": "Kling21Pro_fal", "name": "Kling 2.1 Pro",
     "tasks": ["img2vid"], "quality": 8, "speed": "medium",
     "cost": 0.20, "budget": "balanced", "provider": "kuaishou"},
    {"node": "Veo31Fast_fal", "name": "Veo 3.1 Fast i2v",
     "tasks": ["img2vid", "keyframe_to_clip"], "quality": 9, "speed": "fast",
     "cost_per_sec": 0.15, "budget": "balanced", "provider": "google",
     "notes": "Fast i2v via first_frame input"},
    {"node": "WanPro_fal", "name": "WAN Pro",
     "tasks": ["img2vid"], "quality": 8, "speed": "medium",
     "cost": 0.10, "budget": "eco", "provider": "alibaba"},

    # --- VIDEO: Edit & VFX ---
    {"node": "KlingOmniVideoToVideoEdit_fal", "name": "Kling Omni V2V Edit",
     "tasks": ["video_edit", "vfx"], "quality": 9, "speed": "medium",
     "cost": 0.30, "budget": "balanced", "provider": "kuaishou"},
    {"node": "WanVACEVideoEdit_fal", "name": "WAN VACE Video Edit",
     "tasks": ["video_edit", "vfx"], "quality": 8, "speed": "medium",
     "cost": 0.15, "budget": "balanced", "provider": "alibaba"},
    {"node": "Krea_Wan14b_VideoToVideo_fal", "name": "Krea WAN V2V",
     "tasks": ["video_edit", "style_transfer_video"], "quality": 8, "speed": "medium",
     "cost": 0.10, "budget": "eco", "provider": "krea"},

    # --- VIDEO: Character animation ---
    {"node": "Wan2214b_animate_move_character_fal", "name": "WAN Animate Character",
     "tasks": ["character_animation", "motion"], "quality": 8, "speed": "medium",
     "cost": 0.15, "budget": "balanced", "provider": "alibaba",
     "notes": "Animate a character from single image"},
    {"node": "MiniMaxSubjectReference_fal", "name": "MiniMax Subject Reference",
     "tasks": ["character_animation", "subject_driven_video"], "quality": 8, "speed": "medium",
     "cost": 0.20, "budget": "balanced", "provider": "minimax"},
    {"node": "KlingOmniReferenceToVideo_fal", "name": "Kling Omni Ref2Vid",
     "tasks": ["character_animation", "reference_driven_video"], "quality": 9, "speed": "medium",
     "cost": 0.25, "budget": "premium", "provider": "kuaishou"},

    # --- TRAINING ---
    {"node": "FluxLoraTrainer_fal", "name": "Flux LoRA Trainer",
     "tasks": ["lora_training", "character_training", "style_training"], "quality": 9,
     "speed": "slow", "cost": 2.0, "budget": "premium", "provider": "fal",
     "notes": "Train custom Flux LoRA in the cloud"},
    {"node": "WanLoraTrainer_fal", "name": "WAN LoRA Trainer",
     "tasks": ["lora_training", "video_lora"], "quality": 8, "speed": "slow",
     "cost": 1.5, "budget": "premium", "provider": "alibaba"},
    {"node": "HunyuanVideoLoraTrainer_fal", "name": "Hunyuan Video LoRA Trainer",
     "tasks": ["lora_training", "video_lora"], "quality": 8, "speed": "slow",
     "cost": 1.5, "budget": "premium", "provider": "tencent"},

    # --- VIDEO: Upscale ---
    {"node": "VideoUpscaler_fal", "name": "Video Upscaler (fal.ai)",
     "tasks": ["video_upscale"], "quality": 9, "speed": "medium",
     "cost": 0.10, "budget": "balanced", "provider": "fal"},
    {"node": "Topaz_Upscale_Video_fal", "name": "Topaz Video Upscale",
     "tasks": ["video_upscale"], "quality": 10, "speed": "slow",
     "cost": 0.15, "budget": "premium", "provider": "topaz",
     "notes": "Topaz-quality video upscale"},

    # --- LOCAL (free, CPU) ---
    {"node": "KSampler", "name": "Local KSampler (CPU)",
     "tasks": ["txt2img", "img2img"], "quality": 5, "speed": "very_slow",
     "cost": 0.0, "budget": "eco", "provider": "local",
     "notes": "CPU-only on RPi5, very slow but free. Needs local checkpoint."},
    {"node": "ControlNetApplyAdvanced", "name": "ControlNet (local)",
     "tasks": ["depth_control", "pose_control", "canny_control", "optical_physics"],
     "quality": 8, "speed": "slow", "cost": 0.0, "budget": "eco", "provider": "local",
     "notes": "Local ControlNet for depth/pose/canny guidance"},
]


def get_embedding(text: str) -> list[float]:
    payload = json.dumps({"model": "embedding", "input": text[:8000]}).encode()
    req = urllib.request.Request(
        f"{LITELLM_URL}/v1/embeddings", data=payload,
        headers={"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["data"][0]["embedding"]


def ensure_collection():
    try:
        req = urllib.request.Request(
            f"{QDRANT_URL}/collections/{COLLECTION}",
            headers={"api-key": QDRANT_KEY},
        )
        urllib.request.urlopen(req, timeout=10)
        # Delete and recreate (fresh index)
        req = urllib.request.Request(
            f"{QDRANT_URL}/collections/{COLLECTION}",
            method="DELETE",
            headers={"api-key": QDRANT_KEY},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

    payload = json.dumps({"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}}).encode()
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{COLLECTION}", data=payload, method="PUT",
        headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=15)
    print(f"Created collection '{COLLECTION}'")


def main():
    if not LITELLM_KEY or not QDRANT_KEY:
        print("ERROR: Set LITELLM_KEY and QDRANT_KEY")
        return

    ensure_collection()

    points = []
    for i, model in enumerate(MODELS):
        # Build searchable text
        text = (
            f"{model['name']}: {model.get('notes', '')} "
            f"Tasks: {', '.join(model['tasks'])}. "
            f"Quality: {model['quality']}/10. Speed: {model.get('speed', '?')}. "
            f"Cost: ${model.get('cost', model.get('cost_per_sec', 0))}. "
            f"Provider: {model.get('provider', '?')}. "
            f"Budget: {model['budget']}."
        )

        vector = get_embedding(text)
        point_id = int(hashlib.sha256(model["node"].encode()).hexdigest()[:15], 16)

        points.append({
            "id": point_id,
            "vector": vector,
            "payload": {
                "node": model["node"],
                "name": model["name"],
                "tasks": model["tasks"],
                "quality": model["quality"],
                "speed": model.get("speed", "medium"),
                "cost": model.get("cost", model.get("cost_per_sec", 0)),
                "cost_per_sec": model.get("cost_per_sec"),
                "budget": model["budget"],
                "provider": model.get("provider", "unknown"),
                "text_in_image": model.get("text_in_image", False),
                "max_resolution": model.get("max_resolution", ""),
                "notes": model.get("notes", ""),
                "source": "model-registry",
            },
        })

        if len(points) >= 10:
            payload = json.dumps({"points": points}).encode()
            req = urllib.request.Request(
                f"{QDRANT_URL}/collections/{COLLECTION}/points",
                data=payload, method="PUT",
                headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=30)
            print(f"  [{i+1}/{len(MODELS)}] Upserted {len(points)} models")
            points = []
            time.sleep(0.3)

    if points:
        payload = json.dumps({"points": points}).encode()
        req = urllib.request.Request(
            f"{QDRANT_URL}/collections/{COLLECTION}/points",
            data=payload, method="PUT",
            headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=30)
        print(f"  [{len(MODELS)}/{len(MODELS)}] Upserted {len(points)} models")

    print(f"\nDone: {len(MODELS)} models indexed into '{COLLECTION}'")


if __name__ == "__main__":
    main()
