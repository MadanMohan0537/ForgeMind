import json

from services.perception.events import Event


def test_p1_event_serializes_to_production_core_contract():
    event = Event(
        type="KIT_INSPECTED",
        timestamp=123.5,
        zone="inspection_zone",
        station_id="station_1",
        payload={"detected": {"black_wheel": 2}},
    )

    body = json.loads(event.to_json())

    assert body == {
        "event": "KIT_INSPECTED",
        "payload": {
            "detected": {"black_wheel": 2},
            "timestamp": 123.5,
            "zone": "inspection_zone",
            "station_id": "station_1",
        },
        "source": "perception",
    }
