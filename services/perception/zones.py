"""
Zones are arbitrary named polygons stored as pixel coordinates. Nothing here
assumes there are exactly three of them, or that they're called
inspection_zone/robot_zone/assembly_queue — those names only exist in your
recipe.yaml. Point this at a totally different physical layout and it works
unchanged.
"""

from __future__ import annotations
import json
import os
from typing import Dict, List, Tuple

import cv2
import numpy as np

Point = Tuple[int, int]
Polygon = List[Point]


def load_zones(path: str) -> Dict[str, Polygon]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        raw = json.load(f)
    return {name: [tuple(p) for p in poly] for name, poly in raw.items()}


def save_zones(path: str, zones: Dict[str, Polygon]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(zones, f, indent=2)


def point_in_zone(point: Point, polygon: Polygon) -> bool:
    if not polygon:
        return False
    return cv2.pointPolygonTest(np.array(polygon, dtype=np.int32), point, False) >= 0


def crop_to_zone(frame: np.ndarray, polygon: Polygon) -> Tuple[np.ndarray, np.ndarray]:
    """Returns (cropped_frame, mask) restricted to the zone's bounding box + polygon mask.
    Detectors run against this instead of the full frame, so a part sitting
    outside the zone (e.g. still in someone's hand) never gets counted."""
    if not polygon:
        return frame, np.ones(frame.shape[:2], dtype=np.uint8) * 255

    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 255)
    masked = cv2.bitwise_and(frame, frame, mask=mask)

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x0, x1 = max(min(xs), 0), min(max(xs), frame.shape[1])
    y0, y1 = max(min(ys), 0), min(max(ys), frame.shape[0])
    return masked[y0:y1, x0:x1], mask[y0:y1, x0:x1]


class ZoneCalibrator:
    """Interactive tool: click 4+ points per zone, press 'n' for next zone,
    's' to save, 'q' to quit without saving. Run via scripts/calibrate.py."""

    def __init__(self, zone_names: List[str]):
        self.zone_names = zone_names
        self.zones: Dict[str, Polygon] = {name: [] for name in zone_names}
        self._current = 0

    @property
    def current_zone(self) -> str:
        return self.zone_names[self._current]

    def _on_click(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.zones[self.current_zone].append((x, y))

    def run(self, frame_provider, save_path: str) -> Dict[str, Polygon]:
        window = "calibrate"
        cv2.namedWindow(window)
        cv2.setMouseCallback(window, self._on_click)

        print(f"Calibrating zone: {self.current_zone}")
        print("Click points to draw the polygon. 'n' = next zone, 's' = save, 'q' = quit.")

        while True:
            result = frame_provider()
            if not result.ok:
                continue
            display = result.frame.copy()

            for name, poly in self.zones.items():
                if len(poly) >= 2:
                    color = (0, 255, 0) if name == self.current_zone else (150, 150, 150)
                    pts = np.array(poly, dtype=np.int32)
                    cv2.polylines(display, [pts], isClosed=True, color=color, thickness=2)
                for p in poly:
                    cv2.circle(display, p, 4, (0, 0, 255), -1)

            cv2.putText(display, f"zone: {self.current_zone}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow(window, display)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("n"):
                self._current = (self._current + 1) % len(self.zone_names)
                print(f"Now calibrating: {self.current_zone}")
            elif key == ord("s"):
                save_zones(save_path, self.zones)
                print(f"Saved zones to {save_path}")
            elif key == ord("q"):
                break

        cv2.destroyAllWindows()
        return self.zones
