"""
Detector interface + registry. This is the actual "works on anything" seam.

Today the only implementation is color-blob counting (color_detector.py),
because that's what a hackathon HSV-tunable kit needs. But nothing else in
the pipeline knows that. If you later need to count parts by shape,
template match, or a small ML classifier, you write one more class here,
register it under a new `method` string, and recipe.yaml is the only file
that changes.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Type

import numpy as np


@dataclass
class DetectionResult:
    part_id: str
    count: int
    confidence: float  # 0.0-1.0, this detector's own confidence in the count


class Detector:
    """Subclass this and implement detect(). part_config is whatever dict
    that part's entry in recipe.yaml contains (minus 'id' and 'method')."""

    def __init__(self, part_id: str, part_config: dict):
        self.part_id = part_id
        self.config = part_config

    def detect(self, frame: np.ndarray) -> DetectionResult:
        raise NotImplementedError


_REGISTRY: Dict[str, Type[Detector]] = {}


def register(method_name: str):
    def _wrap(cls: Type[Detector]):
        _REGISTRY[method_name] = cls
        return cls
    return _wrap


def build_detector(part_id: str, part_config: dict) -> Detector:
    method = part_config.get("method")
    if method not in _REGISTRY:
        raise ValueError(
            f"No detector registered for method={method!r} (part {part_id!r}). "
            f"Available methods: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[method](part_id, part_config)


def build_all_detectors(recipe_parts: List[dict]) -> List[Detector]:
    return [build_detector(p["id"], p) for p in recipe_parts]
