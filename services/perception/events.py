"""
Event schema and the client that ships events to Core.

This is the P1 -> P2 contract. If you're wiring this to a real repo that
already has shared/schemas.py, replace the Event dataclass below with an
import from there — everything else in this file (retry/offline-queue
behavior) stays the same regardless of the exact schema shape.

Design choice that matters: perception must NEVER crash or stall because
Core is unreachable. A camera/detection pipeline that blocks on a network
call is a demo-killer. Events that fail to send get queued to a local file
and retried; the perception loop itself never waits on it.
"""

from __future__ import annotations
import json
import os
import time
import threading
import queue
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

import requests


@dataclass
class Event:
    type: str                      # e.g. KIT_ARRIVED, KIT_INSPECTED, KIT_RELEASED, VLM_VERIFICATION
    timestamp: float
    zone: str
    station_id: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class EventClient:
    """Fire-and-forget event sender with retry + offline fallback queue.
    Runs its own background thread so perception's main loop never blocks
    on HTTP."""

    def __init__(
        self,
        events_url: str,
        timeout_seconds: float = 2.0,
        retry_backoff_seconds: Optional[List[float]] = None,
        offline_queue_file: str = "runs/offline_event_queue.jsonl",
    ):
        self.events_url = events_url
        self.timeout = timeout_seconds
        self.backoff = retry_backoff_seconds or [1, 2, 5]
        self.offline_queue_file = offline_queue_file
        os.makedirs(os.path.dirname(offline_queue_file) or ".", exist_ok=True)

        self._q: "queue.Queue[Event]" = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def send(self, event: Event) -> None:
        self._q.put(event)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            self._send_with_retry(event)

    def _send_with_retry(self, event: Event) -> None:
        for delay in [0] + self.backoff:
            if delay:
                time.sleep(delay)
            try:
                resp = requests.post(
                    self.events_url,
                    data=event.to_json(),
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                if resp.status_code < 300:
                    return
            except requests.RequestException:
                pass
        # every retry failed — never drop it, queue to disk for later replay
        self._queue_offline(event)

    def _queue_offline(self, event: Event) -> None:
        with open(self.offline_queue_file, "a") as f:
            f.write(event.to_json() + "\n")

    def flush_offline_queue(self) -> int:
        """Call this on startup (or periodically) to retry anything that
        queued while Core was down. Returns count of events resent."""
        if not os.path.exists(self.offline_queue_file):
            return 0
        with open(self.offline_queue_file, "r") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        if not lines:
            return 0

        os.remove(self.offline_queue_file)
        sent = 0
        for line in lines:
            data = json.loads(line)
            event = Event(**data)
            try:
                resp = requests.post(
                    self.events_url,
                    data=event.to_json(),
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                if resp.status_code < 300:
                    sent += 1
                    continue
            except requests.RequestException:
                pass
            self._queue_offline(event)  # still down, re-queue
        return sent
