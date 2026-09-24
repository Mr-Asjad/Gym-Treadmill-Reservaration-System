from datetime import datetime, timezone

from occupancy import (
    OccupancyTracker,
    occupancy_from_log,
    read_state_log,
    write_state_change,
)


def _change(machine_id, occupied, at="2026-09-07T09:00:00+00:00"):
    return {"zone_id": f"zone-{machine_id[-1]}", "machine_id": machine_id,
            "occupied": occupied, "at": at}


def test_apply_records_latest_state_per_machine():
    t = OccupancyTracker()
    t.apply(_change("treadmill-1", True))
    t.apply(_change("treadmill-2", False))
    assert t.machine_occupancy() == {"treadmill-1": True, "treadmill-2": False}


def test_last_write_wins():
    t = OccupancyTracker()
    t.apply_all([
        _change("treadmill-1", True, "2026-09-07T09:00:00+00:00"),
        _change("treadmill-1", False, "2026-09-07T09:05:00+00:00"),
    ])
    assert t.occupied("treadmill-1") is False
    assert t.since("treadmill-1") == "2026-09-07T09:05:00+00:00"


def test_unknown_machine_is_none():
    assert OccupancyTracker().occupied("treadmill-1") is None


def test_read_state_log_missing_file(tmp_path):
    assert read_state_log(tmp_path / "nope.jsonl") == []


def test_read_state_log_parses_and_skips_blank_lines(tmp_path):
    p = tmp_path / "states.jsonl"
    p.write_text(
        '{"machine_id": "treadmill-1", "occupied": true, "at": "x"}\n'
        "\n"
        '   \n'
        '{"machine_id": "treadmill-1", "occupied": false, "at": "y"}\n',
        encoding="utf-8",
    )
    rows = read_state_log(p)
    assert [r["occupied"] for r in rows] == [True, False]


def test_write_state_change_roundtrips_through_reader(tmp_path):
    p = tmp_path / "states.jsonl"
    at = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    write_state_change(p, "treadmill-1", True, at)
    write_state_change(p, "treadmill-1", False, at)
    rows = read_state_log(p)
    assert [r["occupied"] for r in rows] == [True, False]
    assert rows[0]["machine_id"] == "treadmill-1"
    assert occupancy_from_log(p) == {"treadmill-1": False}


def test_occupancy_from_log_replays_to_current_state(tmp_path):
    p = tmp_path / "states.jsonl"
    p.write_text(
        '{"machine_id": "treadmill-1", "occupied": true, "at": "a"}\n'
        '{"machine_id": "treadmill-2", "occupied": true, "at": "b"}\n'
        '{"machine_id": "treadmill-1", "occupied": false, "at": "c"}\n',
        encoding="utf-8",
    )
    assert occupancy_from_log(p) == {"treadmill-1": False, "treadmill-2": True}
