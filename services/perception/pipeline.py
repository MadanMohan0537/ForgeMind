"""
The P1 perception pipeline. This is the one place all the pieces meet:

    capture -> crop to zone -> run each recipe part's detector -> stabilizer
    -> kit tracker (state transitions) -> event client -> Core

Everything upstream of "which colors/parts to look for" is generic. Point
pipeline.yaml + recipe.yaml at a different object and this file is untouched.
"""

from __future__ import annotations
import time
import logging
from typing import Dict, Optional

import cv2
import yaml

from .capture import open_source, VideoSource
from .zones import load_zones, crop_to_zone
from .recipe import load_recipe, diff_against_recipe, Recipe
from .detectors.base import build_all_detectors
from .detectors import color_detector  # noqa: F401 - import registers "color" method
from .stabilizer import Stabilizer
from .kit_tracker import ZoneTracker
from .events import Event, EventClient
from .vlm_client import VLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [perception] %(message)s")
log = logging.getLogger("perception")


class PerceptionPipeline:
    def __init__(self, pipeline_config_path: str):
        with open(pipeline_config_path, "r") as f:
            self.config = yaml.safe_load(f)

        base_dir = self.config.get("_base_dir", ".")
        self.recipe: Recipe = load_recipe(self._resolve(self.config["recipe_file"]))
        self.zones = load_zones(self._resolve(self.recipe.zones_file))
        if not self.zones:
            log.warning(
                "No zones.json found or it's empty - run scripts/calibrate.py first. "
                "Detection will run against the full frame until zones are calibrated."
            )

        self.detectors = build_all_detectors(self.recipe.parts)
        self.station_id = self.config.get("station_id", "station_1")

        # one stabilizer + tracker per zone, so each physical area's state is independent
        self.stabilizers: Dict[str, Stabilizer] = {
            zone: Stabilizer(self.recipe.required_frames, self.recipe.min_confidence)
            for zone in self.recipe.zone_names
        }
        self.trackers: Dict[str, ZoneTracker] = {
            zone: ZoneTracker(zone_name=zone) for zone in self.recipe.zone_names
        }

        core_cfg = self.config.get("core", {})
        self.event_client = EventClient(
            events_url=core_cfg.get("events_url", "http://127.0.0.1:8100/events"),
            timeout_seconds=core_cfg.get("timeout_seconds", 2),
            retry_backoff_seconds=core_cfg.get("retry_backoff_seconds", [1, 2, 5]),
            offline_queue_file=core_cfg.get("offline_queue_file", "runs/offline_event_queue.jsonl"),
        )
        resent = self.event_client.flush_offline_queue()
        if resent:
            log.info("Resent %d events queued while Core was unreachable", resent)

        vlm_cfg = self.config.get("vlm", {})
        self.vlm_client = VLMClient(
            url=vlm_cfg.get("url", ""),
            timeout_seconds=vlm_cfg.get("timeout_seconds", 3),
            alerts=vlm_cfg.get("alerts", []),
        )

        source_cfg = self.config["source"]
        self.source: VideoSource = open_source(
            source_cfg["kind"], source_cfg.get("uri", ""), loop=source_cfg.get("loop", False)
        )

        rec_cfg = self.config.get("golden_recording", {})
        self._recording = rec_cfg.get("enabled", False)
        self._writer = None
        if self._recording:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(
                rec_cfg["output_path"], fourcc, rec_cfg.get("fps", 15), (640, 480)
            )

    def _resolve(self, path: str) -> str:
        return path  # hook point if you want to make config paths relative to a repo root

    def _run_detectors_for_zone(self, frame, zone_name: str):
        polygon = self.zones.get(zone_name, [])
        cropped, _mask = crop_to_zone(frame, polygon) if polygon else (frame, None)
        if cropped.size == 0:
            cropped = frame

        counts, confidences = {}, {}
        for detector in self.detectors:
            result = detector.detect(cropped)
            counts[result.part_id] = result.count
            confidences[result.part_id] = result.confidence
        return counts, confidences

    def _handle_zone(self, frame, zone_name: str, timestamp: float):
        counts, confidences = self._run_detectors_for_zone(frame, zone_name)
        stable = self.stabilizers[zone_name].update(counts, confidences)

        diff = {"missing": [], "extra": []}
        if stable is not None:
            diff = diff_against_recipe(stable, self.recipe.expected_counts)

        for event_type, payload in self.trackers[zone_name].process(
            stable, diff["missing"], diff["extra"]
        ):
            event = Event(
                type=event_type,
                timestamp=timestamp,
                zone=zone_name,
                station_id=self.station_id,
                payload=payload,
            )
            self.event_client.send(event)
            log.info("Emitted %s zone=%s payload=%s", event_type, zone_name, payload)

            if event_type == "KIT_INSPECTED" and self.vlm_client.enabled:
                self._maybe_emit_vlm_event(frame, zone_name, timestamp)

    def _maybe_emit_vlm_event(self, frame, zone_name: str, timestamp: float):
        for alert_prompt in self.vlm_client.alerts:
            result = self.vlm_client.verify(frame, alert_prompt)
            if result is None:
                continue  # VLM down/slow/not configured - never blocks the main flow
            event = Event(
                type="VLM_VERIFICATION",
                timestamp=timestamp,
                zone=zone_name,
                station_id=self.station_id,
                payload={"prompt": alert_prompt, "result": result},
            )
            self.event_client.send(event)
            log.info("Emitted VLM_VERIFICATION zone=%s prompt=%r", zone_name, alert_prompt)

    def reset_zone(self, zone_name: str):
        """Call after a recovery action so stale stabilizer history doesn't
        create a lagged release (milestone 2's exact failure mode)."""
        if zone_name in self.stabilizers:
            self.stabilizers[zone_name].reset()

    def run_forever(self):
        log.info("Perception pipeline started. Recipe=%s zones=%s", self.recipe.name, list(self.zones.keys()))
        try:
            while True:
                result = self.source.read()
                if not result.ok:
                    log.warning("Frame read failed - source may need attention")
                    time.sleep(0.1)
                    continue

                for zone_name in self.recipe.zone_names:
                    self._handle_zone(result.frame, zone_name, result.timestamp)

                if self._writer is not None:
                    frame_to_write = cv2.resize(result.frame, (640, 480))
                    self._writer.write(frame_to_write)

        except KeyboardInterrupt:
            log.info("Shutting down perception pipeline")
        finally:
            self.source.release()
            if self._writer is not None:
                self._writer.release()
            self.event_client.stop()
