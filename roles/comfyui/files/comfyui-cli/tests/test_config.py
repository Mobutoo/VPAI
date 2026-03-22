"""Tests for config loader."""
import os
import pytest
from pathlib import Path
from comfyui_cli.config import load_config, DEFAULTS


def test_defaults_when_no_file(tmp_path):
    """Config returns defaults when file doesn't exist."""
    config = load_config(tmp_path / "nonexistent.yaml")
    assert config["comfyui_url"] == "http://localhost:8188"
    assert config["git_enabled"] is True


def test_file_overrides(tmp_path):
    """YAML file values override defaults."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("comfyui_url: http://other:9999\n")
    config = load_config(cfg_file)
    assert config["comfyui_url"] == "http://other:9999"
    assert config["workflows_dir"] == DEFAULTS["workflows_dir"]


def test_env_overrides(tmp_path, monkeypatch):
    """Env vars override file values."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("comfyui_url: http://file:1234\n")
    monkeypatch.setenv("COMFYUI_URL", "http://env:5678")
    config = load_config(cfg_file)
    assert config["comfyui_url"] == "http://env:5678"


def test_git_enabled_env_bool(tmp_path, monkeypatch):
    """COMFYUI_GIT_ENABLED env var parsed as bool."""
    monkeypatch.setenv("COMFYUI_GIT_ENABLED", "false")
    config = load_config(tmp_path / "nope.yaml")
    assert config["git_enabled"] is False
