"""
Video source abstraction.

The whole point: everything downstream (calibration, detection, event
emission) reads frames through this one interface. Whether those frames
come from a live RTSP camera, an IP Webcam HTTP stream, a recorded
golden.mp4 file, or a synthetic generator makes zero difference past
this layer. This is what makes "replay fallback" actually trustworthy —
it's the same code path, not a parallel one.
"""

from __future__ import annotations
import time
import itertools
from dataclasses import dataclass
from typing import Optional, Iterator

import cv2
import numpy as np


@dataclass
class FrameResult:
    ok: bool
    frame: Optional[np.ndarray]
    timestamp: float


class VideoSource:
    """Base interface. Subclasses implement read()."""

    def read(self) -> FrameResult:
        raise NotImplementedError

    def release(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


class OpenCVSource(VideoSource):
    """Covers RTSP, HTTP/MJPEG, and file playback — cv2.VideoCapture handles all three
    the same way. `loop` re-opens the file when it ends, for replay-fallback mode."""

    def __init__(self, uri: str, loop: bool = False):
        self.uri = uri
        self.loop = loop
        self.cap = cv2.VideoCapture(uri, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open video source: {uri!r}. "
                f"Check the phone IP, that the RTSP/IP-Webcam app is running, "
                f"and that this device isn't blocked by client isolation on the venue Wi-Fi."
            )

    def read(self) -> FrameResult:
        ok, frame = self.cap.read()
        if not ok and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return FrameResult(ok=ok, frame=frame if ok else None, timestamp=time.time())

    def release(self) -> None:
        self.cap.release()


class SyntheticSource(VideoSource):
    """Generates frames with drawn colored shapes so the whole pipeline can be
    developed and smoke-tested with zero camera hardware. The shapes here are
    a stand-in for the color regions in recipe.yaml's hsv_ranges — swap the
    recipe and this generator still exercises the same detector code paths,
    it just won't match a *different* recipe's colors (which is fine — this
    is a dev/test tool, not a demo fixture).
    """

    def __init__(self, width: int = 640, height: int = 480, missing_part: Optional[str] = None):
        self.w, self.h = width, height
        self.missing_part = missing_part
        self._frame_id = itertools.count()

    def _draw_kit(self, frame, missing_part: Optional[str]):
        # red_body
        if missing_part != "red_body":
            cv2.rectangle(frame, (150, 150), (300, 280), (40, 40, 200), -1)  # BGR red
        # black_wheel x2
        if missing_part != "black_wheel":
            cv2.circle(frame, (180, 300), 25, (20, 20, 20), -1)
            cv2.circle(frame, (270, 300), 25, (20, 20, 20), -1)
        # blue_roof
        if missing_part != "blue_roof":
            cv2.rectangle(frame, (160, 100), (290, 150), (200, 60, 30), -1)  # BGR blue

    def read(self) -> FrameResult:
        frame = np.full((self.h, self.w, 3), 230, dtype=np.uint8)  # light gray table
        cv2.rectangle(frame, (100, 80), (350, 340), (200, 200, 200), 2)  # inspection zone outline
        self._draw_kit(frame, self.missing_part)
        next(self._frame_id)
        return FrameResult(ok=True, frame=frame, timestamp=time.time())


def open_source(kind: str, uri: str, loop: bool = False) -> VideoSource:
    """Factory — this is the one function scripts should call. Add a new
    `kind` here (e.g. a specific SDK camera) without touching anything else."""
    if kind in ("rtsp", "http", "file"):
        return OpenCVSource(uri, loop=loop)
    if kind == "synthetic":
        return SyntheticSource()
    raise ValueError(f"Unknown source kind: {kind!r}")


def frames(source: VideoSource) -> Iterator[FrameResult]:
    while True:
        yield source.read()
