"""Camera stability monitor and guided physical calibration acceptance test."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {"red_body": 1, "black_wheel": 2, "blue_roof": 1}


def fetch_json(url: str, timeout: float = 3.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def sample(base_url: str, seconds: float, interval: float) -> list[dict]:
    readings: list[dict] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            readings.append(fetch_json(f"{base_url.rstrip('/')}/state"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            readings.append({"source_ok": False, "error": str(exc), "fps": 0})
        time.sleep(interval)
    return readings


def stable_counts(readings: list[dict], expected: dict[str, int]) -> bool:
    return bool(readings) and sum(r.get("counts") == expected for r in readings) / len(readings) >= 0.8


def summarize(readings: list[dict]) -> dict:
    fps = [float(r.get("fps", 0)) for r in readings]
    return {
        "samples": len(readings),
        "source_ok_ratio": round(sum(bool(r.get("source_ok")) for r in readings) / max(1, len(readings)), 3),
        "fps_min": round(min(fps, default=0), 2),
        "fps_median": round(statistics.median(fps), 2) if fps else 0,
        "errors": [r["error"] for r in readings if r.get("error")][:10],
    }


def guided(base_url: str, seconds: float, interval: float) -> dict:
    phases = [
        ("complete", "Place a complete kit in the inspection zone and keep it still.", REQUIRED,
         lambda rows: stable_counts(rows, REQUIRED)),
        ("missing_wheel", "Remove one black wheel and keep the kit still.", {**REQUIRED, "black_wheel": 1},
         lambda rows: stable_counts(rows, {**REQUIRED, "black_wheel": 1})),
        ("restored", "Add the wheel back and keep the kit still.", REQUIRED,
         lambda rows: stable_counts(rows, REQUIRED)),
        ("hand", "Move a hand through the robot zone.", None,
         lambda rows: any(r.get("workspace_clear") is False for r in rows)),
        ("empty", "Remove the kit so the inspection zone is empty.", None,
         lambda rows: any(r.get("zone_states", {}).get("inspection_zone", {}).get("state") == "EMPTY" for r in rows)),
    ]
    results = {}
    for name, instruction, expected, validate in phases:
        input(f"\n{name}: {instruction}\nPress Enter when ready...")
        rows = sample(base_url, seconds, interval)
        results[name] = {"ok": bool(validate(rows)), "expected": expected, "summary": summarize(rows)}
        print("PASS" if results[name]["ok"] else "FAIL")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8150")
    parser.add_argument("--duration", type=float, default=600,
                        help="stability-monitor duration in seconds (default: 10 minutes)")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--guided", action="store_true", help="run the five physical acceptance phases")
    parser.add_argument("--phase-seconds", type=float, default=10.0)
    parser.add_argument("--output", default="runs/camera_acceptance.json")
    args = parser.parse_args()

    if args.guided:
        result = {"mode": "guided", "phases": guided(args.url, args.phase_seconds, args.interval)}
        ok = all(phase["ok"] for phase in result["phases"].values())
    else:
        rows = sample(args.url, args.duration, args.interval)
        summary = summarize(rows)
        ok = summary["source_ok_ratio"] >= 0.99 and summary["fps_median"] > 0
        result = {"mode": "stability", "summary": summary}

    result.update({"ok": ok, "timestamp": datetime.now(timezone.utc).isoformat(), "url": args.url})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
