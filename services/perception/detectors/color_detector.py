"""
Generic HSV color-blob detector. It knows nothing about "wheels" or
"bodies" — it just counts blobs matching whatever hsv_ranges + min_area
the recipe gives it for this part_id. Point it at a different recipe and
it'll happily count blue bottle caps or green resistors instead.
"""

from __future__ import annotations
import cv2
import numpy as np

from .base import Detector, DetectionResult, register


@register("color")
class ColorDetector(Detector):
    def __init__(self, part_id: str, part_config: dict):
        super().__init__(part_id, part_config)
        self.hsv_ranges = part_config["hsv_ranges"]      # list of [[h,s,v],[h,s,v]] pairs
        self.min_area = part_config.get("min_area", 300)

    def _mask(self, hsv_frame: np.ndarray) -> np.ndarray:
        mask = np.zeros(hsv_frame.shape[:2], dtype=np.uint8)
        for lower, upper in self.hsv_ranges:
            m = cv2.inRange(hsv_frame, np.array(lower), np.array(upper))
            mask = cv2.bitwise_or(mask, m)
        # clean noise before counting contours — this matters more than threshold precision
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def detect(self, frame: np.ndarray) -> DetectionResult:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = self._mask(hsv)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        valid = [c for c in contours if cv2.contourArea(c) > self.min_area]
        count = len(valid)

        # cheap confidence signal: how consistent are the blob areas?
        # (a clean, evenly-lit blob set has low area variance; a noisy/flickery
        # mask produces wildly different-sized "blobs" that are really noise)
        if count == 0:
            confidence = 1.0 if len(contours) == 0 else 0.3
        else:
            areas = [cv2.contourArea(c) for c in valid]
            mean_area = sum(areas) / len(areas)
            variance = sum((a - mean_area) ** 2 for a in areas) / len(areas)
            rel_std = (variance ** 0.5) / max(mean_area, 1)
            confidence = max(0.0, min(1.0, 1.0 - rel_std))

        return DetectionResult(part_id=self.part_id, count=count, confidence=confidence)
