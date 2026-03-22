"""Configuration loader for comfyui-cli.

Loads from ~/.comfyui-cli.yaml with env var overrides.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".comfyui-cli.yaml"

DEFAULTS = {
    "comfyui_url": "http://localhost:8188",
    "workflows_dir": "/opt/workstation/data/comfyui/user/default/workflows",
    "git_enabled": True,
    "git_author_name": "Claude CLI",
    "git_author_email": "claude@localhost",
    "qdrant_url": "",
    "qdrant_api_key": "",
    "qdrant_collection": "comfyui-docs",
    "litellm_url": "",
    "litellm_api_key": "",
}

ENV_MAP = {
    "COMFYUI_URL": "comfyui_url",
    "COMFYUI_WORKFLOWS_DIR": "workflows_dir",
    "COMFYUI_GIT_ENABLED": "git_enabled",
    "QDRANT_URL": "qdrant_url",
    "QDRANT_API_KEY": "qdrant_api_key",
    "LITELLM_BASE_URL": "litellm_url",
    "LITELLM_API_KEY": "litellm_api_key",
}


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load config from YAML file, then override with env vars."""
    path = config_path or DEFAULT_CONFIG_PATH
    config = dict(DEFAULTS)

    if path.exists():
        with open(path) as f:
            file_config = yaml.safe_load(f) or {}
        config.update(file_config)

    # Env var overrides
    for env_key, config_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            if config_key == "git_enabled":
                config[config_key] = val.lower() in ("true", "1", "yes")
            else:
                config[config_key] = val

    return config
