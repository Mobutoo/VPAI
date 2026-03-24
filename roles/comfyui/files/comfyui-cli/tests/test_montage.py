"""Tests for montage builder."""
import json
import pytest
from comfyui_cli.montage import MontageBuilder, montage_diff


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
