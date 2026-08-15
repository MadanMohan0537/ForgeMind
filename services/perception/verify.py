"""Second-opinion verification with an NVIDIA VLM.

Two paths:
  A) Direct: Cosmos-Reason2-8B (or Nemotron Nano 2 VL) served by vLLM as an OpenAI-compatible endpoint.
     VLM_URL=http://127.0.0.1:8001/v1  VLM_MODEL=cosmos
  B) VSS: once the VSS blueprint is up, point VSS_ASK_URL at its ask/alerts endpoint and fill vss_ask_video().

Both return {"complete": bool, "detected": {...}, "explanation": str, "raw": str}.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Optional

import httpx

VLM_URL = os.environ.get("VLM_URL")              # e.g. http://127.0.0.1:8001/v1
VLM_MODEL = os.environ.get("VLM_MODEL", "cosmos")
VSS_ASK_URL = os.environ.get("VSS_ASK_URL")      # optional VSS endpoint

QUESTION = ("You are inspecting a parts kit for a toy car on a table. A complete kit has exactly 1 red body, "
            "2 black wheels and 1 blue roof. Count what you see inside the marked kit area. "
            'Answer ONLY JSON: {"red_body": <int>, "black_wheel": <int>, "blue_roof": <int>, "explanation": "<short>"}')


def available() -> bool:
    return bool(VLM_URL or VSS_ASK_URL)


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def vlm_verify(image_path: str, timeout: float = 30.0) -> Optional[dict]:
    if VSS_ASK_URL:
        return vss_ask_video(image_path)
    if not VLM_URL:
        return None
    body = {
        "model": VLM_MODEL,
        "temperature": 0.0,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(image_path)}"}},
            {"type": "text", "text": QUESTION},
        ]}],
    }
    r = httpx.post(f"{VLM_URL}/chat/completions", json=body, timeout=timeout,
                   headers={"Authorization": f"Bearer {os.environ.get('VLM_API_KEY', 'none')}"})
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    det = json.loads(m.group(0)) if m else {}
    counts = {k: int(det.get(k, 0) or 0) for k in ("red_body", "black_wheel", "blue_roof")}
    complete = counts == {"red_body": 1, "black_wheel": 2, "blue_roof": 1}
    return {"complete": complete, "detected": counts, "explanation": det.get("explanation", ""), "raw": text[:500],
            "backend": f"vlm:{VLM_MODEL}"}


def vss_ask_video(image_or_clip_path: str) -> Optional[dict]:
    """TODO (Part 4 owner): call the VSS blueprint. Options:
       - the vss-ask-video skill / REST route from the playbook (upload clip, ask QUESTION),
       - or register an alert with vss-manage-alerts and read verified alerts back.
    Return the same dict shape as vlm_verify. Until then, return None so the pipeline keeps working."""
    return None
