from services.core.factoryflow import analyze, supervisor_summary
from services.core.factoryflow_synthetic import demo_events


def test_factoryflow_attributes_visible_bottleneck_to_upstream_station():
    events = demo_events("demo")
    result = analyze("demo", events)
    assert result.observed_bottleneck == "station_b"
    assert result.root_cause_station == "station_a"
    assert result.root_cause == "incomplete_component_transfer"
    assert result.missing_component == "front_right_wheel"
    assert result.affected_stations == ["station_b", "station_c"]
    assert result.assembly_blocked_seconds == 14.0
    assert result.dependency_idle_seconds == 13.0
    assert result.transfer_seconds == {"station_a_to_b": 16.0, "station_b_to_c": 16.0}


def test_factoryflow_summary_does_not_blame_visible_station():
    result = analyze("demo", demo_events("demo"))
    text = supervisor_summary(result)
    assert "visible bottleneck is Station B" in text
    assert "root cause originated at Station A" in text
    assert "before changing Station B staffing" in text


def test_factoryflow_empty_run_is_safe():
    result = analyze("empty", [])
    assert result.root_cause is None
    assert supervisor_summary(result) == "No dependency-chain anomaly was found in this run."
