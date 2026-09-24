from datetime import datetime, timedelta, timezone

import pytest

from models import (
    Booking,
    BookingStatus,
    intervals_overlap,
    reserved_machines,
    to_utc,
)


def _b(machine, start_h, end_h, status=BookingStatus.ACTIVE):
    return Booking(
        id=f"{machine}-{start_h}",
        machine_id=machine,
        member_id="m",
        start=datetime(2026, 9, 2, start_h, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, end_h, tzinfo=timezone.utc),
        status=status,
    )


def test_intervals_overlap_is_half_open():
    a = (datetime(2026, 9, 2, 9), datetime(2026, 9, 2, 10))
    assert intervals_overlap(*a, datetime(2026, 9, 2, 9, 30), datetime(2026, 9, 2, 11))
    # back-to-back does not overlap
    assert not intervals_overlap(*a, datetime(2026, 9, 2, 10), datetime(2026, 9, 2, 11))


def test_booking_rejects_non_positive_window():
    with pytest.raises(ValueError):
        _b("treadmill-1", 10, 10)
    with pytest.raises(ValueError):
        _b("treadmill-1", 11, 10)


def test_booking_rejects_naive_datetime():
    with pytest.raises(ValueError):
        Booking(
            id="x",
            machine_id="treadmill-1",
            member_id="m",
            start=datetime(2026, 9, 2, 9),
            end=datetime(2026, 9, 2, 10),
        )


def test_booking_normalises_to_utc_and_reports_duration():
    plus2 = timezone(timedelta(hours=2))
    b = Booking(
        id="x",
        machine_id="treadmill-1",
        member_id="m",
        start=datetime(2026, 9, 2, 11, tzinfo=plus2),
        end=datetime(2026, 9, 2, 12, tzinfo=plus2),
    )
    assert b.start == datetime(2026, 9, 2, 9, tzinfo=timezone.utc)
    assert b.duration == timedelta(hours=1)


def test_overlaps_respects_machine_and_status():
    a = _b("treadmill-1", 9, 11)
    assert a.overlaps(_b("treadmill-1", 10, 12))
    assert not a.overlaps(_b("treadmill-2", 10, 12))
    assert not a.overlaps(_b("treadmill-1", 11, 12))  # adjacent
    assert not a.overlaps(_b("treadmill-1", 10, 12, status=BookingStatus.CANCELLED))


def test_default_gym_has_two_reserved_machines():
    reserved = reserved_machines()
    assert [m.id for m in reserved] == ["treadmill-1", "treadmill-2"]
