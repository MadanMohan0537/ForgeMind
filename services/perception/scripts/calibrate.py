#!/usr/bin/env python3
"""
Entry point: python scripts/calibrate.py [--config config/pipeline.yaml]

Opens the configured video source and lets you click-draw each zone from
recipe.yaml's zone list. Requires a display (won't work over a headless SSH
session without X forwarding / VNC).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from perception.capture import open_source
from perception.recipe import load_recipe
from perception.zones import ZoneCalibrator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/pipeline.yaml")
    args = parser.parse_args()

    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(args.config) as f:
        config = yaml.safe_load(f)

    recipe = load_recipe(config["recipe_file"])
    source = open_source(config["source"]["kind"], config["source"].get("uri", ""))

    calibrator = ZoneCalibrator(recipe.zone_names)
    calibrator.run(source.read, recipe.zones_file)
    source.release()


if __name__ == "__main__":
    main()
