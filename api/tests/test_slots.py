from datetime import datetime, timedelta, timezone

import config
from models import Booking, Machine

from slots import day_slot_starts, slot_grid

UTC = timezone.utc


class FakeStore:
    def __init__(self, bookings):
        self._b = list(bookings)

    def all(self):
        return list(self._b)


class FakeSvc:
    machines = [
        Machine("treadmill-1", "Reserved Treadmill 1", is_reserved=True),
        Machine("treadmill-2", "Reserved Treadmill 2", is_reserved=True),
        Machine("treadmill-3", "Treadmill 3"),
    ]

    def __init__(self, bookings=()):
        self._b = list(bookings)

    def bookings(self, *, machine_id=None, active_only=False):
        out = [b for b in self._b if machine_id is None or b.machine_id == machine_id]
        return sorted(out, key=lambda b: b.start)


def test_day_slot_starts_span_open_hours():
    tz = UTC
    starts = day_slot_starts(datetime(2026, 9, 9).date(), tz)
    assert starts[0].hour == config.OPEN_HOUR
    assert starts[0].minute == 0
    # last slot ends by CLOSE_HOUR
    assert (starts[-1] + timedelta(minutes=config.SLOT_MINUTES)).hour <= config.CLOSE_HOUR
    step = (starts[1] - starts[0]).total_seconds() / 60
    assert step == config.SLOT_MINUTES


def test_slot_grid_marks_open_booked_mine_past():
    tz = UTC
    day = datetime.now(UTC).date()
    # a booking for someone else at 09:00-09:30 on treadmill-1
    other = Booking("x", "treadmill-1", "m-bo",
                    datetime.combine(day, datetime.min.time(), UTC).replace(hour=9),
                    datetime.combine(day, datetime.min.time(), UTC).replace(hour=9, minute=30))
    mine = Booking("y", "treadmill-2", "m-ada",
                   datetime.combine(day, datetime.min.time(), UTC).replace(hour=10),
                   datetime.combine(day, datetime.min.time(), UTC).replace(hour=10, minute=30))
    svc = FakeSvc([other, mine])

    now = datetime.combine(day, datetime.min.time(), UTC).replace(hour=8)
    rows = slot_grid(svc, day, "m-ada", now, tz, member_name=lambda mid: mid.upper())

    by_label = {r["label"]: r for r in rows}
    assert by_label["09:00"]["cells"][0]["state"] == "booked"
    assert by_label["09:00"]["cells"][0]["member_name"] == "M-BO"
    assert by_label["10:00"]["cells"][1]["state"] == "mine"
    assert by_label["08:00"]["cells"][0]["state"] == "open"  # now is exactly 08:00, not past

    # finished slots drop out of the grid entirely
    now_late = now.replace(hour=12, minute=15)
    rows2 = slot_grid(svc, day, "m-ada", now_late, tz, member_name=lambda mid: mid)
    labels = {r["label"] for r in rows2}
    assert "08:00" not in labels and "11:00" not in labels
    assert "12:00" in labels  # in progress -> still shown
    assert {r["label"]: r for r in rows2}["12:00"]["cells"][0]["state"] == "past"


def test_slot_grid_only_reserved_machines():
    svc = FakeSvc()
    rows = slot_grid(svc, datetime.now(UTC).date(), None, datetime.now(UTC), UTC,
                     member_name=lambda m: m)
    assert all(len(r["cells"]) == 2 for r in rows)
