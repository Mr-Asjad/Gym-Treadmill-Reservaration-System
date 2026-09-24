from datetime import datetime, timedelta, timezone

from models import Booking, Machine

from verdict import (
    IDLE, NO_CAMERA, NO_SHOW, NUDGE, ON_MACHINE, RESERVED_SOON, UNBOOKED_USE,
    WAITING, machine_view, pick_booking, read_events,
)

M = Machine("treadmill-1", "Reserved Treadmill 1", is_reserved=True)
GRACE = timedelta(minutes=5)
NUDGE_WINDOW = timedelta(minutes=3)


def at(h, m=0):
    return datetime(2026, 9, 8, h, m, tzinfo=timezone.utc)


def bk(start_h, end_h, member="m-ada"):
    return Booking("b1", "treadmill-1", member, at(start_h), at(end_h))


def mv(booking, occupied, now, since=None, name="Ada Reyes"):
    return machine_view(
        M, booking, name if booking else None, occupied, since, now,
        grace=GRACE, nudge_window=NUDGE_WINDOW,
    )


# ----------------------------------------------------------------- pick_booking

def test_pick_booking_prefers_current_then_next():
    past = Booking("p", "treadmill-1", "m", at(7), at(8))
    ongoing = Booking("o", "treadmill-1", "m", at(9), at(10))
    later = Booking("l", "treadmill-1", "m", at(11), at(12))
    assert pick_booking([past, later, ongoing], at(9, 30)).id == "o"
    assert pick_booking([past, later], at(9, 30)).id == "l"
    assert pick_booking([past], at(9, 30)) is None


# -------------------------------------------------------------------- verdicts

def test_no_camera_signal():
    assert mv(None, None, at(9, 5)).verdict == NO_CAMERA
    assert mv(bk(9, 10), None, at(9, 5)).verdict == NO_CAMERA  # in window, camera offline


def test_camera_offline_still_shows_upcoming_reservation():
    v = mv(bk(9, 10), None, at(8, 45))
    assert v.verdict == RESERVED_SOON
    assert "Ada Reyes" in v.headline


def test_idle_and_unbooked_use():
    assert mv(None, False, at(9)).verdict == IDLE
    assert mv(None, True, at(9)).verdict == UNBOOKED_USE


def test_reserved_soon_outside_nudge_window():
    assert mv(bk(9, 10), False, at(8, 50)).verdict == RESERVED_SOON
    # occupied but still outside the window -> not a nudge yet
    assert mv(bk(9, 10), True, at(8, 50)).verdict == RESERVED_SOON


def test_nudge_when_occupied_inside_window_before_start():
    v = mv(bk(9, 10), True, at(8, 58))
    assert v.verdict == NUDGE
    assert "Ada Reyes" in v.headline


def test_on_machine_during_window():
    assert mv(bk(9, 10), True, at(9, 15)).verdict == ON_MACHINE


def test_waiting_within_grace_then_no_show():
    assert mv(bk(9, 10), False, at(9, 3)).verdict == WAITING
    assert mv(bk(9, 10), False, at(9, 6)).verdict == NO_SHOW


def test_window_passed_is_idle():
    assert mv(bk(9, 10), False, at(10, 30)).verdict == IDLE


# ------------------------------------------------------------------ read_events

def test_read_events_missing_file(tmp_path):
    assert read_events(tmp_path / "nope.jsonl") == []


def test_read_events_tail_and_skip_blanks(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text(
        '{"type": "booking_created", "at": "2026-09-08T09:00:00+00:00", "data": {}}\n'
        "\n"
        '{"type": "nudge_fired", "at": "2026-09-08T09:01:00+00:00", "data": {}}\n'
        '{"type": "no_show_released", "at": "2026-09-08T09:06:00+00:00", "data": {}}\n',
        encoding="utf-8",
    )
    assert [e["type"] for e in read_events(p)] == [
        "booking_created", "nudge_fired", "no_show_released",
    ]
    assert [e["type"] for e in read_events(p, limit=2)] == [
        "nudge_fired", "no_show_released",
    ]
