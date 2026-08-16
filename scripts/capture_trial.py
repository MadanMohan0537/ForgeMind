"""Start/end a physical trial and save API evidence plus a consistent manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def request_json(url: str, method: str = "GET", body: dict | None = None,
                 token: str = "") -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Forge-Token"] = token
    request = urllib.request.Request(url, data=data, method=method,
                                     headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("baseline", "recovery", "improved"))
    parser.add_argument("--core", default="http://127.0.0.1:8100")
    parser.add_argument("--notes", default="physical trial")
    parser.add_argument("--output-root", default="runs/trials")
    parser.add_argument("--duration", type=float, help="end automatically after this many seconds")
    parser.add_argument("--token", default=os.environ.get("FORGE_TOKEN", ""))
    parser.add_argument("--db", default=os.environ.get("FORGE_DB", "runs/forgemind.sqlite"))
    parser.add_argument("--logs", default="logs")
    args = parser.parse_args()

    started = request_json(f"{args.core}/runs/start", "POST",
                           {"mode": args.mode, "notes": args.notes}, args.token)
    run_id = started["run_id"]
    print(f"Trial {run_id} started. Operate the line from the station pages.")
    try:
        if args.duration:
            time.sleep(args.duration)
        else:
            input("Press Enter when the trial is complete...")
    except KeyboardInterrupt:
        print("\nEnding trial...")

    ended = request_json(f"{args.core}/runs/end", "POST", {}, args.token)
    events = request_json(f"{args.core}/events?run_id={run_id}&limit=10000", token=args.token)
    output = Path(args.output_root) / run_id
    evidence = output / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (output / "events.json").write_text(json.dumps(events, indent=2))
    (output / "metrics.json").write_text(json.dumps(ended.get("metrics", {}), indent=2))

    copied = []
    for event in events:
        value = event.get("evidence_path")
        if not value:
            continue
        source = Path(value)
        if source.is_file():
            target = evidence / source.name
            shutil.copy2(source, target)
            copied.append({"file": str(target.relative_to(output)), "sha256": sha256(target)})

    database = Path(args.db)
    if database.is_file():
        backup_path = output / "event-log.sqlite"
        with sqlite3.connect(database) as source_db, sqlite3.connect(backup_path) as backup_db:
            source_db.backup(backup_db)
        copied.append({"file": str(backup_path.relative_to(output)), "sha256": sha256(backup_path)})

    logs_dir = Path(args.logs)
    if logs_dir.is_dir():
        output_logs = output / "logs"
        output_logs.mkdir(exist_ok=True)
        for source in logs_dir.iterdir():
            if source.is_file():
                target = output_logs / source.name
                shutil.copy2(source, target)
                copied.append({"file": str(target.relative_to(output)), "sha256": sha256(target)})

    manifest = {
        "run_id": run_id,
        "mode": args.mode,
        "notes": args.notes,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "event_count": len(events),
        "artifacts": copied,
        "claims": "Short physical trials demonstrate operation; they do not establish statistical causality.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Saved trial bundle to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
