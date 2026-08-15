"""Store-level tests: kit identity across runs, the legacy migration, event windows."""
from __future__ import annotations

import sqlite3

from shared.schemas import Event, EventType as E, Kit, KitState as S
from services.core.db import Store

LEGACY_SCHEMA = """
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, ts REAL NOT NULL, event TEXT NOT NULL,
  kit_id TEXT, payload TEXT NOT NULL, evidence_path TEXT, source TEXT NOT NULL);
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, mode TEXT NOT NULL, started_ts REAL NOT NULL, ended_ts REAL, notes TEXT);
CREATE TABLE kits (kit_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE analysis (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, kind TEXT NOT NULL, ts REAL NOT NULL, data TEXT NOT NULL);
"""


def test_kit_ids_do_not_collide_across_runs(tmp_path):
    s = Store(str(tmp_path / "c.sqlite"))
    s.save_kit(Kit(kit_id="kit_01", run_id="b1", state=S.HELD, missing={"black_wheel": 1}))
    s.save_kit(Kit(kit_id="kit_01", run_id="r1", state=S.RELEASED))

    assert s.kit("kit_01", "b1").state == S.HELD          # type: ignore[union-attr]
    assert s.kit("kit_01", "r1").state == S.RELEASED      # type: ignore[union-attr]
    assert len(s.kits("b1")) == 1 and len(s.kits("r1")) == 1
    assert s.kit("kit_01", "nosuchrun") is None


def test_legacy_kits_table_is_migrated(tmp_path):
    """A database written by the kit_id-keyed schema keeps its rows and gains the new key."""
    path = str(tmp_path / "legacy.sqlite")
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute("INSERT INTO kits(kit_id, run_id, data) VALUES (?,?,?)",
                 ("kit_01", "b1", Kit(kit_id="kit_01", run_id="b1", state=S.QC_PASS).model_dump_json()))
    conn.execute("INSERT INTO events(run_id, ts, event, kit_id, payload, evidence_path, source) VALUES (?,?,?,?,?,?,?)",
                 ("b1", 1.0, "KIT_STARTED", "kit_01", "{}", None, "station:alice"))
    conn.commit()
    conn.close()

    s = Store(path)
    assert s.kit("kit_01", "b1").state == S.QC_PASS       # type: ignore[union-attr]
    assert len(s.events(run_id="b1")) == 1, "events must survive the migration untouched"

    # the new key now works, and reopening is a no-op
    s.save_kit(Kit(kit_id="kit_01", run_id="r1", state=S.HELD))
    assert len(Store(path).kits()) == 2
    with sqlite3.connect(path) as check:
        left_over = check.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='kits_legacy'").fetchone()[0]
    assert left_over == 0


def _events(run_id: str, n: int) -> list[Event]:
    return [Event(run_id=run_id, ts=float(i), event=E.KIT_STARTED, kit_id=f"kit_{i:02d}") for i in range(1, n + 1)]


def test_event_windows(tmp_path):
    s = Store(str(tmp_path / "c.sqlite"))
    for e in _events("r1", 10):
        s.append(e)

    assert [e.id for e in s.events(run_id="r1", limit=3)] == [1, 2, 3]
    assert [e.id for e in s.events(run_id="r1", limit=3, tail=True)] == [8, 9, 10]
    assert [e.id for e in s.events(run_id="r1", since_id=8)] == [9, 10]
    # tail composes with since_id without reordering the result
    assert [e.id for e in s.events(run_id="r1", since_id=5, limit=2, tail=True)] == [9, 10]


def test_active_run_is_the_newest_unfinished_one(tmp_path):
    s = Store(str(tmp_path / "c.sqlite"))
    s.start_run("b1", "baseline", 100.0)
    s.end_run("b1", 200.0)
    assert s.active_run() is None

    s.start_run("r1", "recovery", 300.0)
    s.start_run("r2", "recovery", 400.0)
    assert s.active_run()["run_id"] == "r2"               # type: ignore[index]
    s.end_run("r2", 500.0)
    assert s.active_run()["run_id"] == "r1"               # type: ignore[index]


def test_last_event_ts(tmp_path):
    s = Store(str(tmp_path / "c.sqlite"))
    s.append(Event(run_id="r1", ts=10.0, event=E.KIT_STARTED, kit_id="kit_01"))
    s.append(Event(run_id="r1", ts=25.0, event=E.KIT_HELD, kit_id="kit_01"))
    s.append(Event(run_id="r1", ts=99.0, event=E.KIT_STARTED, kit_id="kit_02"))

    assert s.last_event_ts("r1", "kit_01") == 25.0
    assert s.last_event_ts("r1", "kit_99") is None
    assert s.last_event_ts("other", "kit_01") is None
