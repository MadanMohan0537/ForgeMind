"""SQLite event store. Events are append-only. Kits/runs/analysis are derived caches."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Iterable, Optional

from shared.schemas import Event, EventType, Kit, KitState

DB_PATH = os.environ.get("FORGE_DB", "runs/forgemind.sqlite")
BUSY_TIMEOUT_SECONDS = float(os.environ.get("FORGE_DB_TIMEOUT", "10"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  ts REAL NOT NULL,
  event TEXT NOT NULL,
  kit_id TEXT,
  payload TEXT NOT NULL,
  evidence_path TEXT,
  source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  started_ts REAL NOT NULL,
  ended_ts REAL,
  notes TEXT
);
-- (run_id, kit_id) is the key, not kit_id alone: kit ids restart at kit_01 every run,
-- so a kit_id-only primary key silently overwrote the previous run's kits.
CREATE TABLE IF NOT EXISTS kits (
  run_id TEXT NOT NULL,
  kit_id TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (run_id, kit_id)
);
CREATE TABLE IF NOT EXISTS analysis (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,        -- hypotheses | experiment | verification
  ts REAL NOT NULL,
  data TEXT NOT NULL
);
"""


class Store:
    """Durable state for core.

    Events are the source of truth and are never updated or deleted. Kits, runs and
    analysis rows are caches that could be rebuilt from the event log.
    """

    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=BUSY_TIMEOUT_SECONDS)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            # On the Spark, perception posts events continuously while the dashboard, the
            # agent poller and the metrics endpoints all read. The default rollback journal
            # makes readers and the writer block each other, which shows up as
            # "database is locked" under exactly the load a live run produces.
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute(f"PRAGMA busy_timeout={int(BUSY_TIMEOUT_SECONDS * 1000)}")
            self._conn.execute("PRAGMA synchronous=NORMAL")     # WAL keeps this crash-safe
            _migrate_kits_key(self._conn)
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- events -----------------------------------------------------------
    def append(self, ev: Event) -> Event:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events(run_id, ts, event, kit_id, payload, evidence_path, source) VALUES (?,?,?,?,?,?,?)",
                (ev.run_id, ev.ts, ev.event.value, ev.kit_id, json.dumps(ev.payload), ev.evidence_path, ev.source),
            )
            self._conn.commit()
            ev.id = cur.lastrowid
            return ev

    def events(self, run_id: Optional[str] = None, since_id: int = 0, limit: int = 5000,
               tail: bool = False) -> list[Event]:
        """Events in id order.

        Args:
            run_id: restrict to one run; None means every run.
            since_id: return only events with a higher id (incremental polling).
            limit: maximum number of rows.
            tail: when the limit truncates, keep the NEWEST rows instead of the oldest.
                Windowed views (the dashboard snapshot) want the tail; incremental
                pollers must leave it False or they skip the middle of the log.
        """
        where = "WHERE id > ?"
        args: list = [since_id]
        if run_id:
            where += " AND run_id = ?"
            args.append(run_id)
        if tail:
            q = f"SELECT * FROM (SELECT * FROM events {where} ORDER BY id DESC LIMIT ?) ORDER BY id ASC"
        else:
            q = f"SELECT * FROM events {where} ORDER BY id ASC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [_row_to_event(r) for r in rows]

    def last_event_ts(self, run_id: str, kit_id: str) -> Optional[float]:
        """Timestamp of the most recent event for one kit (used by the stall watchdog)."""
        with self._lock:
            r = self._conn.execute(
                "SELECT MAX(ts) AS ts FROM events WHERE run_id=? AND kit_id=?", (run_id, kit_id)
            ).fetchone()
        return r["ts"] if r and r["ts"] is not None else None

    def events_by_ids(self, ids: Iterable[int]) -> list[Event]:
        ids = list(ids)
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        with self._lock:
            rows = self._conn.execute(f"SELECT * FROM events WHERE id IN ({marks})", ids).fetchall()
        return [_row_to_event(r) for r in rows]

    # ---- runs ---------------------------------------------------------------
    def start_run(self, run_id: str, mode: str, ts: float, notes: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO runs(run_id, mode, started_ts, ended_ts, notes) VALUES (?,?,?,NULL,?)",
                (run_id, mode, ts, notes),
            )
            self._conn.commit()

    def end_run(self, run_id: str, ts: float) -> None:
        with self._lock:
            self._conn.execute("UPDATE runs SET ended_ts=? WHERE run_id=?", (ts, run_id))
            self._conn.commit()

    def runs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM runs ORDER BY started_ts DESC").fetchall()
        return [dict(r) for r in rows]

    def run(self, run_id: str) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def active_run(self) -> Optional[dict]:
        """The most recently started run that was never ended.

        Core adopts this on startup so a mid-run restart keeps writing to the run the
        operators think they are recording, instead of opening a fresh "scratch" run.
        """
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM runs WHERE ended_ts IS NULL ORDER BY started_ts DESC LIMIT 1"
            ).fetchone()
        return dict(r) if r else None

    # ---- kits ---------------------------------------------------------------
    def save_kit(self, kit: Kit) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kits(run_id, kit_id, data) VALUES (?,?,?)",
                (kit.run_id, kit.kit_id, kit.model_dump_json()),
            )
            self._conn.commit()

    def kit(self, kit_id: str, run_id: Optional[str] = None) -> Optional[Kit]:
        """One kit. Always pass run_id during a run; kit ids repeat across runs."""
        with self._lock:
            if run_id:
                r = self._conn.execute("SELECT data FROM kits WHERE run_id=? AND kit_id=?",
                                       (run_id, kit_id)).fetchone()
            else:
                r = self._conn.execute("SELECT data FROM kits WHERE kit_id=? ORDER BY rowid DESC LIMIT 1",
                                       (kit_id,)).fetchone()
        return Kit.model_validate_json(r["data"]) if r else None

    def kits(self, run_id: Optional[str] = None) -> list[Kit]:
        with self._lock:
            if run_id:
                rows = self._conn.execute("SELECT data FROM kits WHERE run_id=? ORDER BY kit_id", (run_id,)).fetchall()
            else:
                rows = self._conn.execute("SELECT data FROM kits ORDER BY kit_id").fetchall()
        return [Kit.model_validate_json(r["data"]) for r in rows]

    def kits_in_state(self, run_id: str, states: set[KitState]) -> list[Kit]:
        return [k for k in self.kits(run_id) if k.state in states]

    # ---- analysis -----------------------------------------------------------
    def save_analysis(self, run_id: str, kind: str, ts: float, data: dict) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO analysis(run_id, kind, ts, data) VALUES (?,?,?,?)", (run_id, kind, ts, json.dumps(data))
            )
            self._conn.commit()
            return cur.lastrowid

    def latest_analysis(self, run_id: str, kind: str) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute(
                "SELECT data FROM analysis WHERE run_id=? AND kind=? ORDER BY id DESC LIMIT 1", (run_id, kind)
            ).fetchone()
        return json.loads(r["data"]) if r else None


def _migrate_kits_key(conn: sqlite3.Connection) -> None:
    """Move a legacy kits table (primary key kit_id) onto the (run_id, kit_id) key.

    Runs before the schema script, which would otherwise skip the existing table.
    Rows are copied, not dropped: a database written by the old code keeps whichever
    kit rows survived it.
    """
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='kits'").fetchone()
    if not row or "PRIMARY KEY (run_id, kit_id)" in (row["sql"] or ""):
        return
    conn.executescript("""
        ALTER TABLE kits RENAME TO kits_legacy;
        CREATE TABLE kits (
          run_id TEXT NOT NULL,
          kit_id TEXT NOT NULL,
          data TEXT NOT NULL,
          PRIMARY KEY (run_id, kit_id)
        );
        INSERT OR REPLACE INTO kits(run_id, kit_id, data) SELECT run_id, kit_id, data FROM kits_legacy;
        DROP TABLE kits_legacy;
    """)
    conn.commit()


def _row_to_event(r: sqlite3.Row) -> Event:
    return Event(
        id=r["id"], run_id=r["run_id"], ts=r["ts"], event=EventType(r["event"]), kit_id=r["kit_id"],
        payload=json.loads(r["payload"]), evidence_path=r["evidence_path"], source=r["source"],
    )
