"""Shared test fixtures for comfyui-cli."""
import pytest
from unittest.mock import MagicMock
from comfyui_cli.config import DEFAULTS


@pytest.fixture
def mock_config():
    """Default config for tests."""
    return dict(DEFAULTS)


@pytest.fixture
def mock_api():
    """Mock ComfyUI API client."""
    client = MagicMock()
    client.base_url = "http://localhost:8188"
    return client
