"""
Loads recipe.yaml. This is the single file boundary between "generic
perception code" and "what we happen to be inspecting this time."
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List

import yaml


@dataclass
class Recipe:
    name: str
    parts: List[dict]                  # raw part configs, passed straight to detector factory
    expected_counts: Dict[str, int]     # part_id -> expected count
    required_frames: int
    min_confidence: float
    zone_names: List[str]
    zones_file: str


def load_recipe(path: str) -> Recipe:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    expected_counts = {p["id"]: p.get("expected_count", 1) for p in raw["parts"]}

    return Recipe(
        name=raw.get("name", "unnamed_recipe"),
        parts=raw["parts"],
        expected_counts=expected_counts,
        required_frames=raw.get("stability", {}).get("required_frames", 10),
        min_confidence=raw.get("stability", {}).get("min_confidence", 0.6),
        zone_names=raw.get("zones", []),
        zones_file=raw.get("zones_file", "config/zones.json"),
    )


def diff_against_recipe(stable_counts: Dict[str, int], expected: Dict[str, int]) -> dict:
    """Generic missing/extra diff - works for any recipe, any number of parts."""
    missing = []
    extra = []
    for part_id, expected_count in expected.items():
        actual = stable_counts.get(part_id, 0)
        if actual < expected_count:
            missing.append(part_id)
        elif actual > expected_count:
            extra.append(part_id)
    # also catch parts detected that aren't in the recipe at all
    for part_id in stable_counts:
        if part_id not in expected and part_id not in extra:
            extra.append(part_id)
    return {"missing": missing, "extra": extra}
