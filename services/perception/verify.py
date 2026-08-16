"""NVIDIA VLM second-opinion client used by the perception service.

VSS and the direct Cosmos fallback both expose an OpenAI-compatible API.
Configuration is read for every call so it cannot become stale at import time.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

ALERTS = [
    "kit placed in inspection zone",
    "hand in robot zone",
]

_PARTS = ("red_body", "black_wheel", "blue_roof")
_DEFAULT_MAX_MEDIA_BYTES = 50 * 1024 * 1024


class VLMUnavailable(RuntimeError):
    """The VLM is unconfigured, unreachable, or returned an invalid response."""


def _config() -> tuple[str, str]:
    url = os.environ.get("VLM_URL", "").strip()
    model = os.environ.get("VLM_MODEL", "").strip()
    if not url or not model:
        raise VLMUnavailable("VLM_URL and VLM_MODEL must both be set")
    return url.rstrip("/"), model


def available() -> bool:
    """Return whether the service has enough configuration to attempt a call."""
    return bool(os.environ.get("VLM_URL", "").strip() and os.environ.get("VLM_MODEL", "").strip())


def _media_content(path_value: str, media_kind: str) -> dict:
    path = Path(path_value)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise VLMUnavailable(f"media is not readable: {path}") from exc
    max_bytes = int(os.environ.get("VLM_MAX_MEDIA_BYTES", str(_DEFAULT_MAX_MEDIA_BYTES)))
    if size <= 0:
        raise VLMUnavailable(f"media is empty: {path}")
    if size > max_bytes:
        raise VLMUnavailable(f"media exceeds VLM_MAX_MEDIA_BYTES ({size} > {max_bytes}): {path}")

    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise VLMUnavailable(f"media is not readable: {path}") from exc

    fallback = "video/mp4" if media_kind == "video_url" else "image/jpeg"
    mime = mimetypes.guess_type(path.name)[0] or fallback
    return {"type": media_kind, media_kind: {"url": f"data:{mime};base64,{encoded}"}}


def _ask_media(path: str, question: str, media_kind: str, timeout: float) -> dict:
    url, model = _config()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": question},
            _media_content(path, media_kind),
        ]}],
        "temperature": 0,
        "max_tokens": 256,
    }
    req = urlrequest.Request(
        f"{url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.monotonic()
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        answer = body["choices"][0]["message"]["content"]
        if not isinstance(answer, str):
            raise TypeError("message content is not text")
    except (urlerror.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise VLMUnavailable(f"VLM request failed: {exc}") from exc

    return {
        "answer": answer,
        "confidence": None,
        "clip": path,
        "latency_s": round(time.monotonic() - started, 3),
    }


def vss_ask_video(clip_path: str, question: str, timeout: float = 30.0) -> dict:
    """Ask VSS or Cosmos a question about an MP4-compatible video clip."""
    return _ask_media(clip_path, question, "video_url", timeout)


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise VLMUnavailable("VLM verification response did not contain JSON")
    try:
        value = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise VLMUnavailable(f"VLM verification returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise VLMUnavailable("VLM verification response was not an object")
    return value


def vlm_verify(image_path: str, timeout: float = 30.0) -> dict:
    """Count the three kit components in an evidence image for P1."""
    question = (
        "Count the visible toy-car kit parts in the inspection zone. "
        "Return only JSON in this exact shape: "
        '{"detected":{"red_body":0,"black_wheel":0,"blue_roof":0},"notes":"brief evidence"}. '
        "Use non-negative integer counts and do not infer hidden parts."
    )
    result = _ask_media(image_path, question, "image_url", timeout)
    parsed = _json_object(result["answer"])
    raw_detected = parsed.get("detected")
    if not isinstance(raw_detected, dict):
        raise VLMUnavailable("VLM verification JSON has no detected object")
    try:
        detected = {part: max(0, int(raw_detected.get(part, 0))) for part in _PARTS}
    except (TypeError, ValueError) as exc:
        raise VLMUnavailable("VLM verification counts must be integers") from exc
    return {**result, "detected": detected, "notes": str(parsed.get("notes", ""))}


def check_alerts(clip_path: str) -> list[dict]:
    """Evaluate the two registered VSS alert descriptions against a clip."""
    raised = []
    for alert in ALERTS:
        result = vss_ask_video(clip_path, f'Does this clip show: "{alert}"? Answer yes or no and why.')
        if result["answer"].strip().lower().startswith("yes"):
            raised.append({"alert": alert, **result})
    return raised
