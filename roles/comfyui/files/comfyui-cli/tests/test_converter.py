"""Tests for UI-to-API format converter."""
import pytest
from comfyui_cli.converter import is_api_format, ui_to_api


def test_is_api_format_detects_api():
    api_wf = {"3": {"class_type": "KSampler", "inputs": {}}}
    assert is_api_format(api_wf) is True


def test_is_api_format_detects_ui():
    ui_wf = {"nodes": [{"id": 1, "type": "KSampler"}], "links": []}
    assert is_api_format(ui_wf) is False


def test_ui_to_api_simple():
    """Simple workflow with one node and widget values."""
    ui_wf = {
        "nodes": [
            {
                "id": 5,
                "type": "EmptyLatentImage",
                "widgets_values": [512, 768, 1],
                "inputs": [],
            }
        ],
        "links": [],
    }
    object_info = {
        "EmptyLatentImage": {
            "input": {
                "required": {
                    "width": ["INT", {"default": 512}],
                    "height": ["INT", {"default": 512}],
                    "batch_size": ["INT", {"default": 1}],
                },
                "optional": {},
            }
        }
    }

    result = ui_to_api(ui_wf, object_info)
    assert "5" in result
    assert result["5"]["class_type"] == "EmptyLatentImage"
    assert result["5"]["inputs"]["width"] == 512
    assert result["5"]["inputs"]["height"] == 768
    assert result["5"]["inputs"]["batch_size"] == 1


def test_ui_to_api_with_links():
    """Workflow with linked nodes."""
    ui_wf = {
        "nodes": [
            {
                "id": 4,
                "type": "CheckpointLoaderSimple",
                "widgets_values": ["model.safetensors"],
                "inputs": [],
            },
            {
                "id": 6,
                "type": "CLIPTextEncode",
                "widgets_values": ["a cat"],
                "inputs": [{"name": "clip", "link": 1}],
            },
        ],
        "links": [
            [1, 4, 1, 6, 0, "CLIP"],  # link_id=1, from node 4 slot 1, to node 6 slot 0
        ],
    }
    object_info = {
        "CheckpointLoaderSimple": {
            "input": {
                "required": {"ckpt_name": [["model.safetensors"], {}]},
                "optional": {},
            }
        },
        "CLIPTextEncode": {
            "input": {
                "required": {
                    "text": ["STRING", {"default": ""}],
                    "clip": ["CLIP"],
                },
                "optional": {},
            }
        },
    }

    result = ui_to_api(ui_wf, object_info)
    assert result["6"]["inputs"]["text"] == "a cat"
    assert result["6"]["inputs"]["clip"] == ["4", 1]


def test_ui_to_api_skips_reroute():
    """Reroute nodes are excluded from API output."""
    ui_wf = {
        "nodes": [
            {"id": 1, "type": "Reroute", "widgets_values": [], "inputs": []},
            {"id": 2, "type": "Note", "widgets_values": ["hello"], "inputs": []},
        ],
        "links": [],
    }
    result = ui_to_api(ui_wf, {})
    assert len(result) == 0
