import hashlib
from pathlib import Path

from scripts.camera_acceptance import stable_counts, summarize
from scripts.capture_trial import sha256
from scripts.dgx_preflight import available_gib


def test_available_gib_reads_linux_meminfo():
    assert available_gib("MemTotal: 100 kB\nMemAvailable: 20971520 kB\n") == 20.0


def test_camera_acceptance_requires_eighty_percent_stable_counts():
    expected = {"red_body": 1, "black_wheel": 2, "blue_roof": 1}
    rows = [{"counts": expected, "source_ok": True, "fps": 25}] * 8
    rows += [{"counts": {}, "source_ok": True, "fps": 20}] * 2
    assert stable_counts(rows, expected)
    assert summarize(rows)["fps_median"] == 25.0


def test_trial_evidence_hash_is_reproducible():
    artifact = Path("docs/DGX_RUNBOOK.md")
    assert sha256(artifact) == hashlib.sha256(artifact.read_bytes()).hexdigest()
