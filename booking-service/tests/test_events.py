import json

from events import EventLog, EventType


def test_record_and_filter():
    log = EventLog()
    log.record(EventType.BOOKING_CREATED, booking_id="b1")
    log.record(EventType.BOOKING_REJECTED, reason="slot_unavailable")
    log.record(EventType.BOOKING_CREATED, booking_id="b2")

    assert len(log) == 3
    assert [e.data["booking_id"] for e in log.events(EventType.BOOKING_CREATED)] == [
        "b1",
        "b2",
    ]


def test_events_are_timestamped_and_ordered():
    log = EventLog()
    a = log.record(EventType.BOOKING_CREATED, booking_id="b1")
    b = log.record(EventType.BOOKING_CANCELLED, booking_id="b1")
    assert a.at <= b.at
    assert a.at.tzinfo is not None


def test_jsonl_mirror_is_written(tmp_path):
    path = tmp_path / "nested" / "events.jsonl"
    log = EventLog(path)
    log.record(EventType.BOOKING_CREATED, booking_id="b1")
    log.record(EventType.NUDGE_FIRED, machine_id="treadmill-2")

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == "booking_created"
    assert first["data"]["booking_id"] == "b1"
    assert "at" in first
