"""VSS / NVIDIA VLM verification layer (P4).

Provides a second-opinion visual verification on top of OpenCV component
counting, using either NVIDIA VSS (preferred) or the Cosmos VLM fallback.
Both expose an OpenAI-compatible chat completions endpoint, so a single
client implementation covers either backend.

Env vars:
    VLM_URL    e.g. http://127.0.0.1:8001/v1 (VSS or Cosmos, whichever is up)
    VLM_MODEL  e.g. "cosmos" or the VSS blueprint's model name
"""

import base64
import os
import time
from urllib import error as urlerror
from urllib import request as urlrequest
import json

VLM_URL = os.environ.get("VLM_URL")
VLM_MODEL = os.environ.get("VLM_MODEL")

ALERTS = [
    "kit placed in inspection zone",
    "hand in robot zone",
]


class VLMUnavailable(RuntimeError):
    """Raised when VLM_URL/VLM_MODEL aren't configured or the backend is unreachable."""


def _encode_clip(clip_path: str) -> str:
    with open(clip_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def vss_ask_video(clip_path: str, question: str, timeout: float = 30.0) -> dict:
    """Ask the configured VLM (VSS or Cosmos) a question about a video clip.

    Returns:
        {"answer": str, "confidence": float | None, "clip": str, "latency_s": float}

    Raises VLMUnavailable if VLM_URL/VLM_MODEL are unset or the request fails.
    """
    if not VLM_URL or not VLM_MODEL:
        raise VLMUnavailable("VLM_URL and VLM_MODEL must both be set")

    payload = {
        "model": VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {
                        "type": "video_url",
                        "video_url": {"url": f"data:video/mp4;base64,{_encode_clip(clip_path)}"},
                    },
                ],
            }
        ],
        "max_tokens": 256,
    }

    req = urlrequest.Request(
        f"{VLM_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.monotonic()
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError) as e:
        raise VLMUnavailable(f"VLM request failed: {e}") from e
    latency_s = time.monotonic() - start

    answer = body["choices"][0]["message"]["content"]
    return {"answer": answer, "confidence": None, "clip": clip_path, "latency_s": latency_s}


def check_alerts(clip_path: str) -> list[dict]:
    """Run each registered alert question against a clip, return raised alerts."""
    raised = []
    for alert in ALERTS:
        question = f'Does this clip show: "{alert}"? Answer yes or no and why.'
        result = vss_ask_video(clip_path, question)
        if result["answer"].strip().lower().startswith("yes"):
            raised.append({"alert": alert, **result})
    return raised
