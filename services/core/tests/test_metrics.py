from services.core import metrics as M
from services.core.synthetic import run_events


def test_baseline_metrics_shape():
    evs = run_events("baseline_01", "baseline")
    m = M.compute("baseline_01", evs)
    assert m.kits_started == 12
    assert m.incomplete_kits_detected == 3
    assert m.escapes == 3                       # recovery disabled -> all three reached Bob
    assert m.rejected_products == 2
    assert m.correct_products == 10
    assert m.recovery_attempts == 0
    assert m.rework_seconds == 42.0             # 3 * 14
    assert m.missing_part_histogram == {"black_wheel": 3}
    assert m.avg_cycle_seconds and m.avg_cycle_seconds > 30
    assert m.defect_rate == round(2 / 12, 3)


def test_recovery_metrics_shape():
    evs = run_events("recovery_01", "recovery")
    m = M.compute("recovery_01", evs)
    assert m.incomplete_kits_detected == 3
    assert m.escapes == 0
    assert m.recovery_attempts == 3
    assert m.verified_recoveries == 3
    assert m.recovery_success_rate == 1.0
    assert m.rejected_products == 0


def test_compare_and_intervention_reduction():
    b = M.compute("recovery_01", run_events("recovery_01", "recovery"))
    a = M.compute("improved_01", run_events("improved_01", "improved"))
    c = M.compare(b, a)
    assert c["intervention_reduction"] == round((3 - 1) / 3, 3)
    row = {r["metric"]: r for r in c["rows"]}
    assert row["recovery_attempts"]["delta"] == -2


def test_empty_run():
    m = M.compute("nothing", [])
    assert m.kits_started == 0 and m.escape_rate is None
