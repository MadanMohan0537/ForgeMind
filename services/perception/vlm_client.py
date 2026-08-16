"""
Optional second-opinion VLM client. Whether VLM_URL points at VSS or the
Cosmos fallback is P4's problem, not yours - this client just POSTs a frame
and an alert prompt and reports back. If the URL isn't set yet, or the call
fails or times out, this returns None and the main pipeline proceeds exactly
as if VLM verification doesn't exist. It must never be able to block or
break core detection.
"""

from __future__ import annotations
import base64
import time
from typing import List, Optional

import cv2
import numpy as np
import requests


class VLMClient:
    def __init__(self, url: str, timeout_seconds: float = 3.0, alerts: Optional[List[str]] = None):
        self.url = url
        self.timeout = timeout_seconds
        self.alerts = alerts or []

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def verify(self, frame: np.ndarray, alert: str) -> Optional[dict]:
        if not self.enabled:
            return None
        try:
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                return None
            frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            resp = requests.post(
                f"{self.url}/verify",
                json={"image_b64": frame_b64, "prompt": alert},
                timeout=self.timeout,
            )
            if resp.status_code >= 300:
                return None
            return resp.json()
        except requests.RequestException:
            return None  # swallow it - VLM is a bonus signal, never a dependency
