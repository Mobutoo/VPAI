# ComfyUI Studio v0.7.0 — Montage Bridge Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connecter le pipeline de generation ComfyUI Studio au montage Remotion via un format pivot MontageProps, avec ajustements en langage naturel.

**Architecture:** 4 nouveaux MCP tools (`montage_build`, `montage_render`, `montage_adjust`, `montage_diff`) dans le MCP server existant. Cote Python, 2 nouveaux modules (`montage.py`, `montage_agent.py`) dans `comfyui_cli/`. Cote Remotion, le serveur Express API existe deja (`POST /renders`, polling `GET /renders/:jobId`). La v0.5.0 (Series Engine) n'etant pas encore implementee, `montage_build` accepte des assets en entree directe (liste manuelle) — le branchement Series Engine se fera dans une iteration future.

**Tech Stack:** Python 3.11+, MCP SDK (`mcp`), httpx (appels Remotion API), LiteLLM (agent montage_adjust), Remotion (composition Montage existante), Express/TypeScript (serveur render existant)

**Spec:** `docs/specs/SPEC-MONTAGE-BRIDGE-v0.7.0.md`

---

## Etat actuel du codebase

### Ce qui existe

| Composant | Chemin | Etat |
|-----------|--------|------|
| MontageProps types | `roles/remotion/files/remotion/Montage/types.ts` | Complet (SceneData, ArtisticDirection, AudioData, SubtitleLine, TitleData, MontageProps) |
| Composition Montage | `roles/remotion/files/remotion/Montage/Montage.tsx` | Complet (transitions, color grade, grain, subtitles, audio mix) |
| Remotion Express API | `roles/remotion/files/server/index.ts` | Complet (POST /renders, GET /renders/:jobId, DELETE, queue, auth) |
| Render queue | `roles/remotion/files/server/render-queue.ts` | Complet (job queue avec statuts queued/in-progress/done/error) |
| ComfyUI MCP server | `roles/comfyui/files/comfyui-studio/mcp_server.py` | 13 tools, pattern subprocess vers comfyui-cli |
| Config loader | `roles/comfyui/files/comfyui-cli/comfyui_cli/config.py` | YAML + env vars, DEFAULTS dict |
| Ansible role Remotion | `roles/remotion/tasks/main.yml` | Build Docker image, healthcheck |

### Ce qui manque (scope de ce plan)

| Composant | Chemin cible | Responsabilite |
|-----------|-------------|----------------|
| Montage builder | `roles/comfyui/files/comfyui-cli/comfyui_cli/montage.py` | Assembler assets en MontageProps JSON |
| Montage agent | `roles/comfyui/files/comfyui-cli/comfyui_cli/montage_agent.py` | Ajustements LLM sur MontageProps |
| Tests montage | `roles/comfyui/files/comfyui-cli/tests/test_montage.py` | Tests builder + diff |
| Tests agent | `roles/comfyui/files/comfyui-cli/tests/test_montage_agent.py` | Tests agent ajustement |
| Tests render | `roles/comfyui/files/comfyui-cli/tests/test_montage_render.py` | Tests client HTTP render |
| MCP tools (4) | `roles/comfyui/files/comfyui-studio/mcp_server.py` | +4 tools dans le serveur existant |
| Config update | `roles/comfyui/files/comfyui-cli/comfyui_cli/config.py` | +1 key `remotion_api_url` |

---

## Wave 1 — Montage Builder + Config

### Task 1: Ajouter `remotion_api_url` a la config

**Files:**
- Modify: `roles/comfyui/files/comfyui-cli/comfyui_cli/config.py`

- [ ] **Step 1: Ajouter la cle dans DEFAULTS et ENV_MAP**

Dans `config.py`, ajouter dans `DEFAULTS` :
```python
"remotion_api_url": "http://localhost:3200",
"remotion_api_token": "",
"montage_adjust_model": "qwen/qwen3-coder",
```

Et dans `ENV_MAP` :
```python
"REMOTION_API_URL": "remotion_api_url",
"REMOTION_API_TOKEN": "remotion_api_token",
"MONTAGE_ADJUST_MODEL": "montage_adjust_model",
```

- [ ] **Step 2: Verifier que le loader fonctionne**

```bash
cd roles/comfyui/files/comfyui-cli
python3 -c "from comfyui_cli.config import load_config; c = load_config(); print(c['remotion_api_url'], c['remotion_api_token'])"
```
Expected: `http://localhost:3200 ` (token vide par defaut)

- [ ] **Step 3: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/config.py
git commit -m "feat(comfyui): add remotion_api_url + remotion_api_token config keys"
```

---

### Task 2: Creer le module `montage.py` — MontageBuilder

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/montage.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/test_montage.py`

Le builder prend une liste d'assets et produit un MontageProps JSON valide.
Pas de dependance sur Series Engine (v0.5.0) — les assets sont passes directement.

- [ ] **Step 1: Ecrire le test du builder basique**

```python
# tests/test_montage.py
"""Tests for montage builder."""
import json
import pytest
from comfyui_cli.montage import MontageBuilder


class TestMontageBuilder:
    """Test MontageBuilder produces valid MontageProps."""

    def test_build_minimal(self):
        """Build MontageProps from a list of asset URLs."""
        builder = MontageBuilder()
        props = builder.build(
            assets=["https://example.com/scene1.png", "https://example.com/scene2.png"],
            format="reel_9_16",
            pacing="medium",
        )
        assert props["fps"] == 30
        assert props["width"] == 1080
        assert props["height"] == 1920
        assert len(props["scenes"]) == 2
        assert props["scenes"][0]["src"] == "https://example.com/scene1.png"
        assert props["scenes"][0]["durationInFrames"] > 0
        assert props["direction"]["pacing"] == "medium"

    def test_build_landscape(self):
        """Landscape format sets correct dimensions."""
        builder = MontageBuilder()
        props = builder.build(
            assets=["https://example.com/a.png"],
            format="landscape_16_9",
            pacing="fast",
        )
        assert props["width"] == 1920
        assert props["height"] == 1080
        assert props["direction"]["pacing"] == "fast"

    def test_build_square(self):
        """Square format sets 1080x1080."""
        builder = MontageBuilder()
        props = builder.build(
            assets=["https://example.com/a.png"],
            format="square_1_1",
            pacing="slow",
        )
        assert props["width"] == 1080
        assert props["height"] == 1080

    def test_pacing_affects_duration(self):
        """Fast pacing = shorter scenes, slow = longer."""
        builder = MontageBuilder()
        fast = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="fast")
        slow = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="slow")
        assert fast["scenes"][0]["durationInFrames"] < slow["scenes"][0]["durationInFrames"]

    def test_build_with_title(self):
        """Builder can add title card."""
        builder = MontageBuilder()
        props = builder.build(
            assets=["https://example.com/a.png"],
            format="reel_9_16",
            pacing="medium",
            title="Episode 1",
        )
        assert props["title"] is not None
        assert props["title"]["text"] == "Episode 1"
        assert props["title"]["durationInFrames"] > 0

    def test_build_with_brand_style(self):
        """Builder injects brand style into direction."""
        builder = MontageBuilder()
        style = {
            "palette": {"primary": "#FF6B35", "accent": "#2EC4B6"},
            "typography": {"heading": "Montserrat", "body": "Inter"},
            "visual_style": "cinematic",
            "tone": "professional",
        }
        props = builder.build(
            assets=["https://example.com/a.png"],
            format="reel_9_16",
            pacing="medium",
            brand_style=style,
        )
        assert props["direction"]["typography"]["accentColor"] == "#FF6B35"
        assert props["direction"]["typography"]["fontFamily"] == "Montserrat"
        assert props["direction"]["colorGrade"]["preset"] == "teal-orange"

    def test_build_output_is_json_serializable(self):
        """MontageProps output must be JSON-serializable."""
        builder = MontageBuilder()
        props = builder.build(
            assets=["https://example.com/a.png", "https://example.com/b.png"],
            format="reel_9_16",
            pacing="medium",
        )
        serialized = json.dumps(props)
        assert isinstance(serialized, str)
        roundtrip = json.loads(serialized)
        assert roundtrip == props

    def test_build_empty_assets_raises(self):
        """Empty asset list should raise ValueError."""
        builder = MontageBuilder()
        with pytest.raises(ValueError, match="assets"):
            builder.build(assets=[], format="reel_9_16", pacing="medium")

    def test_build_invalid_format_raises(self):
        """Unknown format should raise ValueError."""
        builder = MontageBuilder()
        with pytest.raises(ValueError, match="format"):
            builder.build(assets=["https://example.com/a.png"], format="unknown", pacing="medium")
```

- [ ] **Step 2: Verifier que les tests echouent**

```bash
cd roles/comfyui/files/comfyui-cli
python3 -m pytest tests/test_montage.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'comfyui_cli.montage'`

- [ ] **Step 3: Implementer `montage.py`**

```python
# comfyui_cli/montage.py
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
```

- [ ] **Step 4: Lancer les tests et verifier qu'ils passent**

```bash
cd roles/comfyui/files/comfyui-cli
python3 -m pytest tests/test_montage.py -v
```
Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/montage.py \
       roles/comfyui/files/comfyui-cli/tests/test_montage.py
git commit -m "feat(comfyui): add MontageBuilder — assets to MontageProps"
```

---

### Task 3: Ajouter `montage_diff` au module montage

**Files:**
- Modify: `roles/comfyui/files/comfyui-cli/comfyui_cli/montage.py`
- Modify: `roles/comfyui/files/comfyui-cli/tests/test_montage.py`

- [ ] **Step 1: Ecrire les tests pour diff**

Ajouter dans `tests/test_montage.py` :

```python
from comfyui_cli.montage import MontageBuilder, montage_diff


class TestMontageDiff:
    """Test montage_diff produces readable change list."""

    def test_diff_identical(self):
        """No changes = empty diff."""
        builder = MontageBuilder()
        props = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="medium")
        result = montage_diff(props, props)
        assert result["changes"] == []

    def test_diff_scene_added(self):
        """Detect added scene."""
        builder = MontageBuilder()
        before = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="medium")
        after = builder.build(
            assets=["https://example.com/a.png", "https://example.com/b.png"],
            format="reel_9_16", pacing="medium",
        )
        result = montage_diff(before, after)
        types = [c["type"] for c in result["changes"]]
        assert "scene_added" in types

    def test_diff_scene_duration_changed(self):
        """Detect duration change."""
        builder = MontageBuilder()
        before = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="medium")
        after = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="medium")
        after["scenes"][0]["durationInFrames"] = 60
        result = montage_diff(before, after)
        types = [c["type"] for c in result["changes"]]
        assert "scene_modified" in types

    def test_diff_direction_changed(self):
        """Detect direction changes."""
        builder = MontageBuilder()
        before = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="medium")
        after = builder.build(assets=["https://example.com/a.png"], format="reel_9_16", pacing="medium")
        after["direction"]["grain"] = 0.5
        result = montage_diff(before, after)
        types = [c["type"] for c in result["changes"]]
        assert "direction_changed" in types
```

- [ ] **Step 2: Verifier que les tests echouent**

```bash
python3 -m pytest tests/test_montage.py::TestMontageDiff -v
```
Expected: FAIL — `ImportError: cannot import name 'montage_diff'`

- [ ] **Step 3: Implementer `montage_diff`**

Ajouter a la fin de `montage.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests**

```bash
python3 -m pytest tests/test_montage.py -v
```
Expected: 13 tests PASS (9 builder + 4 diff)

- [ ] **Step 5: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/montage.py \
       roles/comfyui/files/comfyui-cli/tests/test_montage.py
git commit -m "feat(comfyui): add montage_diff — compare two MontageProps"
```

---

## Wave 2 — Montage Render + Montage Adjust

### Task 4: Creer `montage_render.py` — client HTTP vers Remotion API

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/montage_render.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/test_montage_render.py`

Le Remotion server existe deja avec `POST /renders` (cree un job) et `GET /renders/:jobId` (polling).
Ce module est un client HTTP qui appelle ces endpoints.

- [ ] **Step 1: Ecrire les tests (avec mock HTTP)**

```python
# tests/test_montage_render.py
"""Tests for montage render client."""
import json
import pytest
from unittest.mock import patch, MagicMock
from comfyui_cli.montage_render import MontageRenderer


def _make_props():
    """Minimal valid MontageProps."""
    return {
        "scenes": [{"type": "keyframe", "src": "https://example.com/a.png",
                     "durationInFrames": 120, "sceneIndex": 0}],
        "fps": 30, "width": 1080, "height": 1920,
        "direction": {
            "pacing": "medium", "defaultTransition": "crossfade",
            "defaultTransitionDurationFrames": 15,
            "colorGrade": {"preset": "none", "contrast": 1, "saturation": 1, "brightness": 1},
            "grain": 0,
            "typography": {"fontFamily": "Inter", "accentColor": "#3b82f6", "textColor": "#fff"},
            "subtitleStyle": "cinema",
        },
    }


class TestMontageRenderer:
    """Test MontageRenderer HTTP client."""

    @patch("comfyui_cli.montage_render.httpx")
    def test_submit_render(self, mock_httpx):
        """Submit a render job to Remotion API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jobId": "abc-123"}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        renderer = MontageRenderer(api_url="http://localhost:3200")
        job_id = renderer.submit(_make_props())

        assert job_id == "abc-123"
        mock_httpx.post.assert_called_once()
        call_args = mock_httpx.post.call_args
        assert call_args[0][0] == "http://localhost:3200/renders"
        body = call_args[1]["json"]
        assert body["compositionId"] == "Montage"
        assert body["inputProps"] == _make_props()

    @patch("comfyui_cli.montage_render.httpx")
    def test_poll_status(self, mock_httpx):
        """Poll job status from Remotion API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobId": "abc-123", "status": "completed",
            "videoUrl": "http://localhost:3200/renders/abc-123.mp4",
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.get.return_value = mock_response

        renderer = MontageRenderer(api_url="http://localhost:3200")
        result = renderer.poll("abc-123")

        assert result["status"] == "completed"
        assert "videoUrl" in result

    @patch("comfyui_cli.montage_render.httpx")
    def test_submit_with_auth_token(self, mock_httpx):
        """Auth token is sent as Bearer header."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"jobId": "abc-123"}
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        renderer = MontageRenderer(api_url="http://localhost:3200", api_token="secret")
        renderer.submit(_make_props())

        call_args = mock_httpx.post.call_args
        assert call_args[1]["headers"]["Authorization"] == "Bearer secret"

    @patch("comfyui_cli.montage_render.httpx")
    def test_render_and_wait(self, mock_httpx):
        """render() submits then polls until done."""
        post_response = MagicMock()
        post_response.status_code = 200
        post_response.json.return_value = {"jobId": "abc-123"}
        post_response.raise_for_status = MagicMock()

        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "jobId": "abc-123", "status": "completed",
            "videoUrl": "http://localhost:3200/renders/abc-123.mp4",
        }
        get_response.raise_for_status = MagicMock()

        mock_httpx.post.return_value = post_response
        mock_httpx.get.return_value = get_response

        renderer = MontageRenderer(api_url="http://localhost:3200")
        result = renderer.render(_make_props())

        assert result["status"] == "completed"
        assert result["videoUrl"].endswith(".mp4")

    @patch("comfyui_cli.montage_render.httpx")
    @patch("comfyui_cli.montage_render.time")
    def test_submit_retries_on_429(self, mock_time, mock_httpx):
        """Submit retries with backoff when queue is full (429)."""
        resp_429 = MagicMock()
        resp_429.status_code = 429

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.json.return_value = {"jobId": "abc-123"}
        resp_ok.raise_for_status = MagicMock()

        mock_httpx.post.side_effect = [resp_429, resp_ok]
        mock_time.sleep = MagicMock()

        renderer = MontageRenderer(api_url="http://localhost:3200")
        job_id = renderer.submit(_make_props())

        assert job_id == "abc-123"
        assert mock_httpx.post.call_count == 2
        mock_time.sleep.assert_called_once_with(5)  # 2^0 * 5

    @patch("comfyui_cli.montage_render.httpx")
    @patch("comfyui_cli.montage_render.time")
    def test_submit_raises_queue_full_after_retries(self, mock_time, mock_httpx):
        """Submit raises QueueFullError after max retries on 429."""
        resp_429 = MagicMock()
        resp_429.status_code = 429

        mock_httpx.post.return_value = resp_429
        mock_time.sleep = MagicMock()

        from comfyui_cli.montage_render import QueueFullError
        renderer = MontageRenderer(api_url="http://localhost:3200", max_submit_retries=2)
        with pytest.raises(QueueFullError, match="queue full"):
            renderer.submit(_make_props())

    @patch("comfyui_cli.montage_render.httpx")
    @patch("comfyui_cli.montage_render.time")
    def test_render_raises_on_cancelled(self, mock_time, mock_httpx):
        """render() raises RenderError if job is cancelled."""
        post_response = MagicMock()
        post_response.status_code = 200
        post_response.json.return_value = {"jobId": "abc-123"}
        post_response.raise_for_status = MagicMock()

        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {"jobId": "abc-123", "status": "cancelled"}
        get_response.raise_for_status = MagicMock()

        mock_httpx.post.return_value = post_response
        mock_httpx.get.return_value = get_response
        mock_time.monotonic = MagicMock(side_effect=[0, 1])
        mock_time.sleep = MagicMock()

        from comfyui_cli.montage_render import RenderError
        renderer = MontageRenderer(api_url="http://localhost:3200")
        with pytest.raises(RenderError, match="cancelled"):
            renderer.render(_make_props())
```

- [ ] **Step 2: Verifier l'echec**

```bash
python3 -m pytest tests/test_montage_render.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implementer `montage_render.py`**

```python
# comfyui_cli/montage_render.py
"""HTTP client for the Remotion render API.

The Remotion Express server (localhost:3200) exposes:
  POST /renders    — create a render job (returns jobId)
  GET  /renders/:id — poll job status (queued | in-progress | completed | failed)
"""
import time
from typing import Any, Dict, Optional

import httpx


class RenderError(Exception):
    """Raised when a render job fails."""


class QueueFullError(RenderError):
    """Raised when the Remotion render queue is full (HTTP 429)."""


class MontageRenderer:
    """Client for the Remotion render API."""

    def __init__(
        self,
        api_url: str = "http://localhost:3200",
        api_token: Optional[str] = None,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        max_submit_retries: int = 3,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.max_submit_retries = max_submit_retries

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def submit(self, montage_props: Dict[str, Any]) -> str:
        """Submit a render job. Returns job ID.

        Retries up to max_submit_retries on 429 (queue full) with exponential backoff.
        """
        for attempt in range(self.max_submit_retries):
            resp = httpx.post(
                f"{self.api_url}/renders",
                json={"compositionId": "Montage", "inputProps": montage_props},
                headers=self._headers(),
                timeout=30.0,
            )
            if resp.status_code == 429:
                if attempt < self.max_submit_retries - 1:
                    time.sleep(2 ** attempt * 5)  # 5s, 10s, 20s
                    continue
                raise QueueFullError(
                    f"Render queue full after {self.max_submit_retries} retries "
                    f"(max 10 concurrent jobs)")
            resp.raise_for_status()
            return resp.json()["jobId"]
        raise QueueFullError("Render queue full")  # unreachable but satisfies type checker

    def poll(self, job_id: str) -> Dict[str, Any]:
        """Poll job status once. Returns job dict."""
        resp = httpx.get(
            f"{self.api_url}/renders/{job_id}",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    def render(self, montage_props: Dict[str, Any]) -> Dict[str, Any]:
        """Submit and poll until complete. Returns final job dict.

        Raises:
            RenderError: If job fails, is cancelled, or times out.
            QueueFullError: If render queue is full after retries.
        """
        job_id = self.submit(montage_props)
        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:
            result = self.poll(job_id)
            status = result.get("status", "")

            if status == "completed":
                return result
            if status == "failed":
                raise RenderError(f"Render failed: {result.get('error', 'unknown')}")
            if status == "cancelled":
                raise RenderError(f"Render cancelled (job: {job_id})")

            time.sleep(self.poll_interval)

        raise RenderError(f"Render timed out after {self.timeout}s (job: {job_id})")
```

- [ ] **Step 4: Lancer les tests**

```bash
python3 -m pytest tests/test_montage_render.py -v
```
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/montage_render.py \
       roles/comfyui/files/comfyui-cli/tests/test_montage_render.py
git commit -m "feat(comfyui): add MontageRenderer — HTTP client for Remotion API"
```

---

### Task 5: Creer `montage_agent.py` — ajustements LLM

**Files:**
- Create: `roles/comfyui/files/comfyui-cli/comfyui_cli/montage_agent.py`
- Test: `roles/comfyui/files/comfyui-cli/tests/test_montage_agent.py`

L'agent recoit un MontageProps + une instruction en langage naturel,
appelle LiteLLM pour produire un MontageProps modifie.

- [ ] **Step 1: Ecrire les tests (avec mock LLM)**

```python
# tests/test_montage_agent.py
"""Tests for montage adjustment agent."""
import json
import pytest
from unittest.mock import patch, MagicMock
from comfyui_cli.montage_agent import MontageAgent


def _make_props():
    """Minimal MontageProps for testing."""
    return {
        "scenes": [
            {"type": "keyframe", "src": "https://example.com/a.png",
             "durationInFrames": 120, "sceneIndex": 0},
            {"type": "keyframe", "src": "https://example.com/b.png",
             "durationInFrames": 120, "sceneIndex": 1},
        ],
        "fps": 30, "width": 1080, "height": 1920,
        "direction": {
            "pacing": "medium", "defaultTransition": "crossfade",
            "defaultTransitionDurationFrames": 15,
            "colorGrade": {"preset": "none", "contrast": 1.0,
                           "saturation": 1.0, "brightness": 1.0},
            "grain": 0,
            "typography": {"fontFamily": "Inter", "accentColor": "#3b82f6",
                           "textColor": "#fff"},
            "subtitleStyle": "cinema",
        },
    }


class TestMontageAgent:
    """Test MontageAgent adjustments via LLM."""

    @patch("comfyui_cli.montage_agent.httpx")
    def test_adjust_returns_modified_props(self, mock_httpx):
        """Agent returns a modified MontageProps dict."""
        modified = _make_props()
        modified["scenes"][0]["durationInFrames"] = 60

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(modified)}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        agent = MontageAgent(litellm_url="http://localhost:4000/v1",
                             litellm_api_key="test")
        result = agent.adjust(_make_props(), "raccourcis la scene 1 de 2 secondes")

        assert result["montage_props"]["scenes"][0]["durationInFrames"] == 60
        assert "diff" in result

    @patch("comfyui_cli.montage_agent.httpx")
    def test_adjust_validates_output(self, mock_httpx):
        """Agent validates that LLM output has required fields."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"fps": 30})}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        agent = MontageAgent(litellm_url="http://localhost:4000/v1",
                             litellm_api_key="test")
        with pytest.raises(ValueError, match="scenes"):
            agent.adjust(_make_props(), "change something")

    @patch("comfyui_cli.montage_agent.httpx")
    def test_adjust_includes_diff(self, mock_httpx):
        """Result includes a diff of what changed."""
        modified = _make_props()
        modified["direction"]["grain"] = 0.3

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(modified)}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_response

        agent = MontageAgent(litellm_url="http://localhost:4000/v1",
                             litellm_api_key="test")
        result = agent.adjust(_make_props(), "ajoute du grain")

        assert len(result["diff"]["changes"]) > 0
```

- [ ] **Step 2: Verifier l'echec**

```bash
python3 -m pytest tests/test_montage_agent.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implementer `montage_agent.py`**

```python
# comfyui_cli/montage_agent.py
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
```

- [ ] **Step 4: Lancer les tests**

```bash
python3 -m pytest tests/test_montage_agent.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/comfyui_cli/montage_agent.py \
       roles/comfyui/files/comfyui-cli/tests/test_montage_agent.py
git commit -m "feat(comfyui): add MontageAgent — LLM-driven montage adjustments"
```

---

## Wave 3 — MCP Tools Integration

### Task 6: Ajouter les 4 MCP tools au serveur

**Files:**
- Modify: `roles/comfyui/files/comfyui-studio/mcp_server.py`

Les 4 tools appellent directement les modules Python (pas subprocess) car ils manipulent
des dicts JSON complexes — le pattern subprocess serait trop fragile.

- [ ] **Step 1: Ajouter les imports et initialisation en haut du fichier**

Apres les imports existants dans `mcp_server.py`, ajouter :

```python
# Montage bridge modules (direct import, not subprocess — complex JSON I/O)
import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "comfyui-cli"))
from comfyui_cli.config import load_config
from comfyui_cli.montage import MontageBuilder, montage_diff
from comfyui_cli.montage_render import MontageRenderer
from comfyui_cli.montage_agent import MontageAgent

_config = load_config()
_montage_builder = MontageBuilder()
_montage_renderer = MontageRenderer(
    api_url=_config.get("remotion_api_url", "http://localhost:3200"),
    api_token=_config.get("remotion_api_token") or None,
)
_montage_agent = MontageAgent(
    litellm_url=_config.get("litellm_url", ""),
    litellm_api_key=_config.get("litellm_api_key", ""),
    model=_config.get("montage_adjust_model", "qwen/qwen3-coder"),
) if _config.get("litellm_url") else None
```

- [ ] **Step 2: Ajouter les 4 Tool definitions dans list_tools()**

Ajouter dans le `return [...]` de `list_tools()` :

```python
        Tool(
            name="montage_build",
            description="Assemble assets into a MontageProps JSON ready for Remotion render",
            inputSchema={
                "type": "object",
                "properties": {
                    "assets": {
                        "type": "array", "items": {"type": "string"},
                        "description": "List of asset URLs (images or videos)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["reel_9_16", "landscape_16_9", "square_1_1"],
                        "description": "Output format",
                    },
                    "pacing": {
                        "type": "string", "enum": ["fast", "medium", "slow"],
                        "description": "Pacing preset",
                    },
                    "title": {"type": "string", "description": "Optional title card text"},
                    "brand_style": {
                        "type": "object",
                        "description": "Optional brand style (palette, typography, tone)",
                    },
                },
                "required": ["assets", "format", "pacing"],
            },
        ),
        Tool(
            name="montage_render",
            description="Send MontageProps to Remotion and return render result (MP4)",
            inputSchema={
                "type": "object",
                "properties": {
                    "montage_props": {
                        "type": "object", "description": "MontageProps JSON",
                    },
                    "quality": {
                        "type": "string", "enum": ["draft", "final"],
                        "description": "Render quality: draft (720p) or final (1080p). Default: draft",
                        "default": "draft",
                    },
                },
                "required": ["montage_props"],
            },
        ),
        Tool(
            name="montage_adjust",
            description="Modify a MontageProps via natural language instruction (uses LLM)",
            inputSchema={
                "type": "object",
                "properties": {
                    "montage_props": {
                        "type": "object", "description": "Current MontageProps JSON",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Natural language edit instruction",
                    },
                },
                "required": ["montage_props", "instruction"],
            },
        ),
        Tool(
            name="montage_diff",
            description="Compare two MontageProps and return a readable list of changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "before": {"type": "object", "description": "Original MontageProps"},
                    "after": {"type": "object", "description": "Modified MontageProps"},
                },
                "required": ["before", "after"],
            },
        ),
```

- [ ] **Step 3: Ajouter les handlers dans call_tool()**

Ajouter avant le `else: output = json.dumps({"error": ...})` :

```python
        elif name == "montage_build":
            props = _montage_builder.build(
                assets=arguments["assets"],
                format=arguments["format"],
                pacing=arguments["pacing"],
                title=arguments.get("title"),
                brand_style=arguments.get("brand_style"),
            )
            output = json.dumps(props)

        elif name == "montage_render":
            props = arguments["montage_props"]
            quality = arguments.get("quality", "draft")
            if quality == "draft":
                props = {**props, "width": min(props.get("width", 1080), 1280),
                         "height": min(props.get("height", 1920), 1280)}
            result = _montage_renderer.render(props)
            output = json.dumps(result)

        elif name == "montage_adjust":
            if _montage_agent is None:
                output = json.dumps(
                    {"error": "LiteLLM not configured — set litellm_url in config"})
            else:
                result = _montage_agent.adjust(
                    montage_props=arguments["montage_props"],
                    instruction=arguments["instruction"],
                )
                output = json.dumps(result)

        elif name == "montage_diff":
            result = montage_diff(arguments["before"], arguments["after"])
            output = json.dumps(result)
```

- [ ] **Step 4: Verifier la syntaxe**

```bash
python3 -c "import ast; ast.parse(open('roles/comfyui/files/comfyui-studio/mcp_server.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add roles/comfyui/files/comfyui-studio/mcp_server.py
git commit -m "feat(comfyui): add 4 montage MCP tools (build, render, adjust, diff)"
```

---

### Task 7: Ajouter `httpx` aux dependances

**Files:**
- Modify: `roles/comfyui/files/comfyui-cli/setup.py`

- [ ] **Step 1: Lire setup.py et ajouter httpx dans install_requires**

Ajouter `"httpx>=0.27,<1"` dans la liste `install_requires` de `setup.py` :

```python
install_requires=[
    "click>=8.1,<9",
    "httpx>=0.27,<1",
    "requests>=2.31,<3",
    "pyyaml>=6.0,<7",
],
```

- [ ] **Step 2: Commit**

```bash
git add roles/comfyui/files/comfyui-cli/setup.py
git commit -m "feat(comfyui): add httpx dependency for montage render client"
```

---

### Task 8: Tests finaux et lint

- [ ] **Step 1: Lancer la suite complete**

```bash
cd roles/comfyui/files/comfyui-cli
python3 -m pytest tests/test_montage.py tests/test_montage_render.py tests/test_montage_agent.py -v
```
Expected: 23 tests PASS (9 builder + 4 diff + 7 render + 3 agent)

- [ ] **Step 2: Verifier le lint**

```bash
source /home/mobuone/VPAI/.venv/bin/activate
cd /home/mobuone/VPAI
make lint
```
Expected: PASS (ou warnings non-bloquants)

---

## Diagramme de dependances

```
Task 1 (config)
    |
    v
Task 2 (builder) ---> Task 3 (diff)
    |                      |
    v                      v
Task 4 (render)       Task 5 (agent) --- depends on ---> Task 3 (diff)
    |                      |
    +----------+-----------+
               |
               v
         Task 6 (MCP tools) ---> Task 7 (deps) ---> Task 8 (tests finaux)
```

**Parallelisable :** Tasks 2+3 et Tasks 4+5 peuvent etre executees en parallele (apres Task 1).

---

## Hors scope (a planifier separement)

| Item | Quand | Prerequis |
|------|-------|-----------|
| Branchement Series Engine (`series_id` + `episode_num` dans montage_build) | Apres v0.5.0 | Series Engine implemente — ajoutera ces params au schema MCP (breaking change) |
| Pacing `"dynamic"` (duree par scene variable) | Apres v0.5.0 | Series Engine pour metadata duree par scene |
| `montage_render` output `"preview"` (URL Remotion Player) | Apres API render valide | Server endpoint `/preview` |
| OpenCut bridge (import/export MontageProps) | v0.7.0 Wave 3 optionnel | Fork OpenCut ou Option B fichier |
| Ansible deployment (config Waza, env vars) | Apres validation locale | Tests passent |
