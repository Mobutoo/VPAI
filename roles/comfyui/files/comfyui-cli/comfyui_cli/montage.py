"""Montage builder — assemble assets into MontageProps JSON.

Produces a MontageProps dict compatible with the Remotion Montage composition.
See: roles/remotion/files/remotion/Montage/types.ts for the TypeScript contract.
"""
from typing import Any, Dict, List, Optional


# Format presets: (width, height)
FORMATS = {
    "reel_9_16": (1080, 1920),
    "landscape_16_9": (1920, 1080),
    "square_1_1": (1080, 1080),
}

# Pacing presets: frames per scene at 30fps
# Note: TypeScript ArtisticDirection also defines "dynamic" pacing —
# not supported in v0.7.0 (requires per-scene duration logic from Series Engine).
PACING_FRAMES = {
    "fast": 60,      # 2s
    "medium": 120,    # 4s
    "slow": 210,      # 7s
}

# Tone -> color grade preset mapping
TONE_COLOR_MAP = {
    "professional": "teal-orange",
    "playful": "warm",
    "luxe": "bleach-bypass",
    "urban": "cold",
    "cinematic": "teal-orange",
}


class MontageBuilder:
    """Assemble a list of assets into a MontageProps dict."""

    def build(
        self,
        assets: List[str],
        format: str,
        pacing: str,
        title: Optional[str] = None,
        brand_style: Optional[Dict[str, Any]] = None,
        fps: int = 30,
    ) -> Dict[str, Any]:
        if not assets:
            raise ValueError("assets list must not be empty")
        if format not in FORMATS:
            raise ValueError(f"Unknown format: {format!r}. Valid: {list(FORMATS)}")
        if pacing not in PACING_FRAMES:
            raise ValueError(f"Unknown pacing: {pacing!r}. Valid: {list(PACING_FRAMES)}")

        width, height = FORMATS[format]
        scene_frames = PACING_FRAMES[pacing]

        scenes = []
        for i, asset_url in enumerate(assets):
            scenes.append({
                "type": "keyframe",
                "src": asset_url,
                "durationInFrames": scene_frames,
                "sceneIndex": i,
                "kenBurns": {
                    "startScale": 1.0,
                    "endScale": 1.1,
                    "panX": 0,
                    "panY": 0,
                },
            })

        direction = self._build_direction(pacing, brand_style)

        props: Dict[str, Any] = {
            "scenes": scenes,
            "fps": fps,
            "width": width,
            "height": height,
            "direction": direction,
        }

        if title:
            props["title"] = {
                "text": title,
                "subtitle": "",
                "color": direction["typography"]["textColor"],
                "backgroundColor": "#000000",
                "durationInFrames": fps * 2,
                "animation": "fade",
            }

        return props

    def _build_direction(
        self, pacing: str, brand_style: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        typography = {
            "fontFamily": "Inter, sans-serif",
            "accentColor": "#3b82f6",
            "textColor": "#ffffff",
        }
        color_preset = "none"
        grain = 0.0

        if brand_style:
            palette = brand_style.get("palette", {})
            typo = brand_style.get("typography", {})
            tone = brand_style.get("tone", "")

            if palette.get("primary"):
                typography["accentColor"] = palette["primary"]
            if typo.get("heading"):
                typography["fontFamily"] = typo["heading"]

            color_preset = TONE_COLOR_MAP.get(tone, "none")
            if brand_style.get("visual_style") == "cinematic":
                grain = 0.15

        transition_frames = {"fast": 8, "medium": 15, "slow": 25}

        return {
            "pacing": pacing,
            "defaultTransition": "crossfade",
            "defaultTransitionDurationFrames": transition_frames.get(pacing, 15),
            "colorGrade": {
                "preset": color_preset,
                "contrast": 1.0,
                "saturation": 1.0,
                "brightness": 1.0,
            },
            "grain": grain,
            "typography": typography,
            "subtitleStyle": "cinema",
        }


def montage_diff(
    before: Dict[str, Any], after: Dict[str, Any]
) -> Dict[str, Any]:
    """Compare two MontageProps and return a readable diff.

    Returns:
        Dict with "changes" list, each item has "type", "description", and optional "details".
    """
    changes: List[Dict[str, Any]] = []

    # Compare scenes
    before_scenes = before.get("scenes", [])
    after_scenes = after.get("scenes", [])

    max_len = max(len(before_scenes), len(after_scenes))
    for i in range(max_len):
        if i >= len(before_scenes):
            changes.append({
                "type": "scene_added",
                "description": f"Scene {i} added",
                "details": {"src": after_scenes[i].get("src", "")},
            })
        elif i >= len(after_scenes):
            changes.append({
                "type": "scene_removed",
                "description": f"Scene {i} removed",
                "details": {"src": before_scenes[i].get("src", "")},
            })
        elif before_scenes[i] != after_scenes[i]:
            diffs = {
                k: {"before": before_scenes[i].get(k), "after": after_scenes[i].get(k)}
                for k in set(list(before_scenes[i].keys()) + list(after_scenes[i].keys()))
                if before_scenes[i].get(k) != after_scenes[i].get(k)
            }
            changes.append({
                "type": "scene_modified",
                "description": f"Scene {i} modified: {', '.join(diffs.keys())}",
                "details": diffs,
            })

    # Compare direction
    if before.get("direction") != after.get("direction"):
        before_dir = before.get("direction", {})
        after_dir = after.get("direction", {})
        diffs = {
            k: {"before": before_dir.get(k), "after": after_dir.get(k)}
            for k in set(list(before_dir.keys()) + list(after_dir.keys()))
            if before_dir.get(k) != after_dir.get(k)
        }
        changes.append({
            "type": "direction_changed",
            "description": f"Direction changed: {', '.join(diffs.keys())}",
            "details": diffs,
        })

    # Compare title/outro
    for key in ("title", "outro"):
        if before.get(key) != after.get(key):
            changes.append({
                "type": f"{key}_changed",
                "description": f"{key.capitalize()} card changed",
                "details": {"before": before.get(key), "after": after.get(key)},
            })

    # Compare audio
    if before.get("audio") != after.get("audio"):
        changes.append({
            "type": "audio_changed",
            "description": "Audio config changed",
            "details": {"before": before.get("audio"), "after": after.get("audio")},
        })

    return {"changes": changes}
