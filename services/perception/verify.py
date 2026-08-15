"""VSS / NVIDIA VLM verification layer (P4).

Provides a second-opinion visual verification on top of OpenCV component
counting, using either NVIDIA VSS (preferred) or the Cosmos VLM fallback.

Env vars expected (set by whichever path comes up first):
    VLM_URL    e.g. http://127.0.0.1:8001/v1
    VLM_MODEL  e.g. "cosmos" or the VSS blueprint's model name
"""

import os

VLM_URL = os.environ.get("VLM_URL")
VLM_MODEL = os.environ.get("VLM_MODEL")


def vss_ask_video(clip_path: str, question: str) -> dict:
    """Ask the configured VLM a question about a video clip.

    Returns a dict shaped like:
        {"answer": str, "confidence": float, "clip": str}

    TODO(P4): implement VSS call when VSS_URL is up; fall back to
    serve_cosmos.sh + this same interface otherwise.
    """
    raise NotImplementedError("wire up VSS or Cosmos client here")


ALERTS = [
    "kit placed in inspection zone",
    "hand in robot zone",
]
