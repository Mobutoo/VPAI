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
