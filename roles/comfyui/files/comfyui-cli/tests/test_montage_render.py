"""Tests for montage render client."""
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
