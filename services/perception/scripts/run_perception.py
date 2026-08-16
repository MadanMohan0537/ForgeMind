#!/usr/bin/env python3
"""
Entry point: python scripts/run_perception.py [--config config/pipeline.yaml]

Reads pipeline.yaml + recipe.yaml, opens whatever source is configured
(rtsp/http/file/synthetic), and runs forever, emitting events to Core.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perception.pipeline import PerceptionPipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/pipeline.yaml")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pipeline = PerceptionPipeline(args.config)
    pipeline.run_forever()


if __name__ == "__main__":
    main()
