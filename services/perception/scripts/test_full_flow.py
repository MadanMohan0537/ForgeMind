#!/usr/bin/env python3
"""
Simulates milestone 1 + milestone 2 end-to-end through the REAL pipeline
components (detectors, stabilizer, kit tracker, event client) against a
running mock Core, using a scripted sequence of synthetic frames:

  empty table -> complete kit arrives -> hold steady 10 frames -> COMPLETE
  -> wheel removed -> hold steady 10 frames -> HELD missing black_wheel
  -> wheel added back -> hold steady 10 frames -> COMPLETE -> RELEASED

This is what "no manual correction" actually looks like as a test, not just
a live demo you eyeball once.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perception.recipe import load_recipe, diff_against_recipe
from perception.detectors.base import build_all_detectors
from perception.detectors import color_detector  # noqa: F401
from perception.capture import SyntheticSource
from perception.stabilizer import Stabilizer
from perception.kit_tracker import ZoneTracker
from perception.events import Event, EventClient

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

recipe = load_recipe("config/recipe.yaml")
detectors = build_all_detectors(recipe.parts)
stabilizer = Stabilizer(recipe.required_frames, recipe.min_confidence)
tracker = ZoneTracker(zone_name="inspection_zone")
client = EventClient(events_url="http://127.0.0.1:5001/events", offline_queue_file="runs/test_offline_queue.jsonl")

received_log = []


def feed_frames(missing_part, n_frames, empty=False):
    """Runs n_frames of detection+stabilization+tracking for a given table state."""
    if empty:
        # simulate an empty inspection zone: zero counts for every part
        for _ in range(n_frames):
            counts = {d.part_id: 0 for d in detectors}
            confs = {d.part_id: 1.0 for d in detectors}
            stable = stabilizer.update(counts, confs)
            diff = diff_against_recipe(stable, recipe.expected_counts) if stable else {"missing": [], "extra": []}
            for event_type, payload in tracker.process(stable, diff["missing"], diff["extra"]):
                emit(event_type, payload)
        return

    source = SyntheticSource(missing_part=missing_part)
    for _ in range(n_frames):
        frame = source.read().frame
        counts, confs = {}, {}
        for d in detectors:
            r = d.detect(frame)
            counts[r.part_id] = r.count
            confs[r.part_id] = r.confidence
        stable = stabilizer.update(counts, confs)
        diff = diff_against_recipe(stable, recipe.expected_counts) if stable else {"missing": [], "extra": []}
        for event_type, payload in tracker.process(stable, diff["missing"], diff["extra"]):
            emit(event_type, payload)


def emit(event_type, payload):
    event = Event(type=event_type, timestamp=time.time(), zone="inspection_zone",
                  station_id="test_station", payload=payload)
    client.send(event)
    received_log.append((event_type, payload))
    print(f"  -> {event_type}  {payload}")


print("Step 1: empty table (baseline, no events expected)")
feed_frames(None, recipe.required_frames + 2, empty=True)

print("\nStep 2: complete kit placed, should stabilize and fire KIT_ARRIVED + KIT_INSPECTED(complete)")
feed_frames(missing_part=None, n_frames=recipe.required_frames + 2)

print("\nStep 3: wheel removed (MILESTONE 1) - expect KIT_INSPECTED missing=['black_wheel']")
stabilizer.reset()  # simulate the physical change invalidating stale history
feed_frames(missing_part="black_wheel", n_frames=recipe.required_frames + 2)

print("\nStep 4: wheel added back (MILESTONE 2) - expect KIT_INSPECTED missing=[]")
stabilizer.reset()
feed_frames(missing_part=None, n_frames=recipe.required_frames + 2)

print("\nStep 5: kit removed from table entirely - expect KIT_RELEASED")
stabilizer.reset()
feed_frames(None, recipe.required_frames + 2, empty=True)

time.sleep(1.5)  # let the async event client flush to Core
client.stop()

print("\n=== Event sequence emitted ===")
for t, p in received_log:
    print(f"{t:16s} {p}")

assert received_log[0][0] == "KIT_ARRIVED"
assert any(e[0] == "KIT_INSPECTED" and e[1]["missing"] == [] for e in received_log[:2]), "expected an early complete inspection"
milestone1 = [e for e in received_log if e[0] == "KIT_INSPECTED" and "black_wheel" in e[1].get("missing", [])]
assert milestone1, "MILESTONE 1 FAILED: no KIT_INSPECTED event reported missing black_wheel"
milestone2_idx = received_log.index(milestone1[-1])
milestone2 = [e for e in received_log[milestone2_idx+1:] if e[0] == "KIT_INSPECTED" and e[1]["missing"] == []]
assert milestone2, "MILESTONE 2 FAILED: no re-inspection after wheel replaced released the kit"
assert received_log[-1][0] == "KIT_RELEASED", "expected the sequence to end with KIT_RELEASED"

print("\nALL MILESTONES PASSED (1 and 2), full sequence behaved correctly.")
