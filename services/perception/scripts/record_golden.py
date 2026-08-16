#!/usr/bin/env python3
"""
Entry point: python scripts/record_golden.py --seconds 60

Records straight from the configured live source to runs/golden.mp4,
independent of the detection pipeline, so you get a clean plate to replay
from if the live camera has to be swapped out mid-recording. Run this once
detection is already working reliably - this file's whole value is being a
GOOD run.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import yaml
from perception.capture import open_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/pipeline.yaml")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", default="runs/golden.mp4")
    parser.add_argument("--fps", type=int, default=15)
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(args.config) as f:
        config = yaml.safe_load(f)

    source = open_source(config["source"]["kind"], config["source"].get("uri", ""))
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    writer = None
    start = time.time()
    frame_count = 0
    print(f"Recording {args.seconds}s to {args.output} ...")

    try:
        while time.time() - start < args.seconds:
            result = source.read()
            if not result.ok:
                continue
            if writer is None:
                h, w = result.frame.shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(args.output, fourcc, args.fps, (w, h))
            writer.write(result.frame)
            frame_count += 1
    finally:
        source.release()
        if writer is not None:
            writer.release()

    print(f"Done. Wrote {frame_count} frames to {args.output}")


if __name__ == "__main__":
    main()
