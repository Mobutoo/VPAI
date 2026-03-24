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
