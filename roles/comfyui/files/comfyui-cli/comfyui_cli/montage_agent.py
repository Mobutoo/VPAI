"""Montage adjustment agent — modify MontageProps via natural language.

Sends the current MontageProps + a user instruction to LiteLLM,
gets back a modified MontageProps, validates it, and returns the diff.
"""
import json
from typing import Any, Dict

import httpx

from comfyui_cli.montage import montage_diff

SYSTEM_PROMPT = """\
You are a video montage editor. You receive a MontageProps JSON and an instruction.
Return ONLY the modified MontageProps JSON — no explanation, no markdown, no extra text.
Preserve all fields. Only modify what the instruction asks for.

MontageProps structure:
- scenes[]: each has type, src, durationInFrames, sceneIndex, optional kenBurns/overlay
- direction: pacing, defaultTransition, defaultTransitionDurationFrames, colorGrade, \
grain, typography, subtitleStyle
- title/outro: optional TitleData with text, color, backgroundColor, durationInFrames, animation
- audio: optional AudioData
- fps, width, height: do not change unless explicitly asked

Rules:
- durationInFrames must be > 0
- sceneIndex must match array position
- transitions: cut, crossfade, dip-to-black, wipe, slide
- colorGrade presets: none, warm, cold, teal-orange, vintage, bleach-bypass
- fps is always 30 (1 second = 30 frames)
"""

REQUIRED_FIELDS = {"scenes", "fps", "width", "height", "direction"}


class MontageAgent:
    """Adjust MontageProps via LLM instruction."""

    def __init__(self, litellm_url: str, litellm_api_key: str,
                 model: str = "qwen/qwen3-coder"):
        self.litellm_url = litellm_url.rstrip("/")
        self.litellm_api_key = litellm_api_key
        self.model = model

    def adjust(
        self, montage_props: Dict[str, Any], instruction: str
    ) -> Dict[str, Any]:
        """Apply a natural-language instruction to a MontageProps.

        Returns:
            Dict with "montage_props" (modified) and "diff" (changes list).

        Raises:
            ValueError: If LLM output is not valid MontageProps.
        """
        resp = httpx.post(
            f"{self.litellm_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.litellm_api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Current MontageProps:\n```json\n"
                        f"{json.dumps(montage_props, indent=2)}\n```\n\n"
                        f"Instruction: {instruction}"
                    )},
                ],
                "temperature": 0.1,
            },
            timeout=60.0,
        )
        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]

        # Strip markdown fences if present
        if content.strip().startswith("```"):
            lines = content.strip().split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        modified = json.loads(content)
        self._validate(modified)

        diff = montage_diff(montage_props, modified)

        return {"montage_props": modified, "diff": diff}

    def _validate(self, props: Dict[str, Any]) -> None:
        """Validate that output has required MontageProps fields."""
        missing = REQUIRED_FIELDS - set(props.keys())
        if missing:
            raise ValueError(f"LLM output missing required fields: {missing}")

        if not isinstance(props.get("scenes"), list) or len(props["scenes"]) == 0:
            raise ValueError("scenes must be a non-empty list")

        for i, scene in enumerate(props["scenes"]):
            dur = scene.get("durationInFrames", 0)
            if not isinstance(dur, (int, float)) or dur <= 0:
                raise ValueError(
                    f"Scene {i}: durationInFrames must be > 0, got {dur}")
