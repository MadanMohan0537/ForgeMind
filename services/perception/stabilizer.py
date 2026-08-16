"""
A single-frame detector reading is noisy - a shadow, a hand passing through,
a compression artifact can all flip a count for one frame. This module only
reports a reading as "trustworthy" once it's held steady across N consecutive
frames, which is what milestone 3 ("steadily for 10 seconds") actually means
in code.

Generic over however many parts the recipe defines - it doesn't know part
names, just dicts of {part_id: count}.
"""

from __future__ import annotations
from collections import deque
from typing import Dict, Optional


class Stabilizer:
    def __init__(self, required_frames: int = 10, min_confidence: float = 0.6):
        self.required_frames = required_frames
        self.min_confidence = min_confidence
        self._counts: "deque[Dict[str, int]]" = deque(maxlen=required_frames)
        self._confidences: "deque[Dict[str, float]]" = deque(maxlen=required_frames)

    def reset(self) -> None:
        """Call this right after a physical change is expected (e.g. right after
        a recovery action) so stale history doesn't create a lagged release."""
        self._counts.clear()
        self._confidences.clear()

    def update(
        self, counts: Dict[str, int], confidences: Dict[str, float]
    ) -> Optional[Dict[str, int]]:
        """Feed one frame's reading. Returns the stable count dict once
        `required_frames` consecutive frames agree and clear the confidence
        floor, otherwise None."""
        self._counts.append(dict(counts))
        self._confidences.append(dict(confidences))

        if len(self._counts) < self.required_frames:
            return None

        first = self._counts[0]
        if any(c != first for c in self._counts):
            return None

        avg_conf = {
            part_id: sum(c.get(part_id, 0.0) for c in self._confidences) / len(self._confidences)
            for part_id in first
        }
        if any(v < self.min_confidence for v in avg_conf.values()):
            return None

        return first

    def overall_confidence(self) -> float:
        if not self._confidences:
            return 0.0
        latest = self._confidences[-1]
        if not latest:
            return 0.0
        return sum(latest.values()) / len(latest)
