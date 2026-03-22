"""ComfyUI HTTP API client.

Wraps all ComfyUI REST endpoints used by the CLI.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests


class ComfyUIClient:
    """HTTP client for ComfyUI API."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(
            f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )

    def _post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(
            f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )

    # --- System ---

    def system_stats(self) -> Dict[str, Any]:
        """GET /system_stats"""
        return self._get("/system_stats").json()

    # --- Workflows (userdata) ---
    #
    # ComfyUI routes use /userdata/{file} where {file} is a single aiohttp
    # path parameter. Slashes MUST be URL-encoded (%2F) so aiohttp matches
    # the entire "workflows/name.json" as one {file} segment.

    @staticmethod
    def _userdata_path(path: str) -> str:
        """Encode a userdata relative path for aiohttp {file} matching."""
        return quote(f"workflows/{path}", safe="")

    def list_workflows(self) -> List[str]:
        """GET /userdata?dir=workflows — list workflow files."""
        resp = self._get("/userdata", params={"dir": "workflows", "recurse": "true"})
        resp.raise_for_status()
        return resp.json()

    def get_workflow(self, path: str) -> Dict[str, Any]:
        """GET /userdata/<encoded_path> — read workflow JSON."""
        resp = self._get(f"/userdata/{self._userdata_path(path)}")
        resp.raise_for_status()
        return resp.json()

    def save_workflow(self, path: str, data: Dict[str, Any]) -> None:
        """POST /userdata/<encoded_path> — save workflow JSON."""
        resp = self._post(
            f"/userdata/{self._userdata_path(path)}",
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
            params={"overwrite": "true"},
        )
        resp.raise_for_status()

    def delete_workflow(self, path: str) -> None:
        """DELETE /userdata/<encoded_path>"""
        resp = self.session.delete(
            f"{self.base_url}/userdata/{self._userdata_path(path)}",
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def move_workflow(self, old_path: str, new_path: str) -> None:
        """POST /userdata/<old>/move/<new> — rename/move."""
        resp = self._post(
            f"/userdata/{self._userdata_path(old_path)}/move/{self._userdata_path(new_path)}",
        )
        resp.raise_for_status()

    # --- Execution ---

    def queue_prompt(self, prompt: Dict[str, Any], client_id: str = "") -> Dict:
        """POST /prompt — queue a workflow for execution."""
        payload = {"prompt": prompt}
        if client_id:
            payload["client_id"] = client_id
        resp = self._post("/prompt", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_queue(self) -> Dict[str, Any]:
        """GET /queue — running + pending items."""
        return self._get("/queue").json()

    def cancel(self, prompt_id: Optional[str] = None) -> None:
        """Cancel a specific prompt or interrupt + clear all."""
        if prompt_id:
            self._post("/queue", json={"delete": [prompt_id]})
        else:
            # Interrupt currently running + clear pending queue
            self._post("/interrupt")
            self._post("/queue", json={"clear": True})

    def get_history(self, limit: int = 10) -> Dict[str, Any]:
        """GET /history — execution history."""
        return self._get("/history", params={"max_items": str(limit)}).json()

    def get_prompt_output(self, prompt_id: str) -> Dict[str, Any]:
        """GET /history/<prompt_id> — specific execution result."""
        resp = self._get(f"/history/{prompt_id}")
        resp.raise_for_status()
        data = resp.json()
        return data.get(prompt_id, {})

    # --- Introspection ---

    def get_object_info(self, node_class: Optional[str] = None) -> Dict[str, Any]:
        """GET /object_info[/<class>] — node class metadata."""
        path = f"/object_info/{node_class}" if node_class else "/object_info"
        return self._get(path).json()

    def get_models(self, folder: Optional[str] = None) -> Any:
        """GET /models[/<folder>] — available models."""
        path = f"/models/{folder}" if folder else "/models"
        return self._get(path).json()

    def upload_image(self, file_path: str, subfolder: str = "") -> Dict[str, Any]:
        """POST /upload/image — upload an image file."""
        import mimetypes
        mime_type = mimetypes.guess_type(file_path)[0] or "image/png"
        with open(file_path, "rb") as f:
            files = {"image": (Path(file_path).name, f, mime_type)}
            data = {}
            if subfolder:
                data["subfolder"] = subfolder
            resp = self._post("/upload/image", files=files, data=data)
        resp.raise_for_status()
        return resp.json()

    def get_view(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """GET /view — download an output image."""
        resp = self._get(
            "/view",
            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
        )
        resp.raise_for_status()
        return resp.content

    # --- Polling ---

    def wait_for_completion(self, prompt_id: str, poll_interval: float = 2.0, timeout: float = 300.0) -> Dict:
        """Poll /history until prompt_id appears with status."""
        start = time.time()
        while time.time() - start < timeout:
            history = self.get_history(limit=50)
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False) or status.get("status_str") == "success":
                    return entry
                if status.get("status_str") == "error":
                    return entry
            time.sleep(poll_interval)
        raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")
