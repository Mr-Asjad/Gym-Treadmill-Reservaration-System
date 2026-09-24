from datetime import datetime, timedelta, timezone

from occupancy import ZoneOccupancyMonitor, ZoneState
from zones import Zone

T0 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
ZONES = [
    Zone("zone-1", "T1", "treadmill-1", (0.0, 0.0, 0.5, 1.0)),
    Zone("zone-2", "T2", "treadmill-2", (0.5, 0.0, 1.0, 1.0)),
]


def monitor(occupied_after=1.0, vacant_after=2.0):
    return ZoneOccupancyMonitor(ZONES, occupied_after=occupied_after, vacant_after=vacant_after)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def test_empty_room_stays_empty():
    m = monitor()
    for s in range(5):
        assert m.update({}, at(s)) == []
    assert m.status("zone-1").state == ZoneState.EMPTY


def test_occupied_only_after_the_debounce_window():
    m = monitor(occupied_after=1.0)
    assert m.update({"zone-1": {1}}, at(0.0)) == []   # first sighting
    assert m.update({"zone-1": {1}}, at(0.5)) == []   # still within window
    changes = m.update({"zone-1": {1}}, at(1.0))      # window elapsed
    assert [(c.machine_id, c.occupied) for c in changes] == [("treadmill-1", True)]
    assert m.status("zone-1").occupied


def test_brief_gap_during_accumulation_does_not_restart_the_clock():
    # someone is present from t=0; the detector drops one frame at t=0.4
    m = monitor(occupied_after=1.0, vacant_after=2.0)
    m.update({"zone-1": {1}}, at(0.0))
    m.update({}, at(0.4))                              # missed frame, gap < vacant_after
    m.update({"zone-1": {1}}, at(0.8))
    changes = m.update({"zone-1": {1}}, at(1.0))       # 1.0s since first seen
    assert [(c.machine_id, c.occupied) for c in changes] == [("treadmill-1", True)]


def test_presence_fully_lapsing_restarts_the_clock():
    m = monitor(occupied_after=1.0, vacant_after=1.0)
    m.update({"zone-1": {1}}, at(0.0))
    m.update({}, at(0.5))
    m.update({}, at(1.6))                              # gap > vacant_after -> lapsed
    assert m.update({"zone-1": {1}}, at(2.0)) == []    # clock restarted at 2.0
    assert m.status("zone-1").state == ZoneState.EMPTY
    assert m.update({"zone-1": {1}}, at(3.0)) != []    # ...occupied 1.0s later


def test_vacate_only_after_grace_and_brief_dropout_is_ignored():
    m = monitor(occupied_after=0.0, vacant_after=2.0)
    m.update({"zone-1": {1}}, at(0.0))                 # occupied immediately
    assert m.status("zone-1").occupied
    m.update({}, at(1.0))                              # 1s gap - still occupied
    assert m.status("zone-1").occupied
    m.update({"zone-1": {1}}, at(1.5))                 # back - resets last_seen
    m.update({}, at(3.0))                              # 1.5s gap
    assert m.status("zone-1").occupied
    changes = m.update({}, at(3.6))                    # now 2.1s since last_seen
    assert [(c.machine_id, c.occupied) for c in changes] == [("treadmill-1", False)]


def test_zones_are_independent_and_counts_are_reported():
    m = monitor(occupied_after=0.0)
    m.update({"zone-1": {1, 2}}, at(0.0))
    assert m.status("zone-1").person_count == 2
    assert m.status("zone-2").state == ZoneState.EMPTY
    assert len(m.changes) == 1


def test_snapshot_is_a_detached_copy():
    m = monitor(occupied_after=0.0)
    m.update({"zone-1": {1}}, at(0.0))
    snap = m.snapshot()
    snap["zone-1"].person_count = 999
    assert m.status("zone-1").person_count == 1
