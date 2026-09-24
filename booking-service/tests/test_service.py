from datetime import datetime, timedelta, timezone

import pytest

from events import EventType
from service import (
    BookingService,
    InvalidWindow,
    MachineNotReservable,
    MemberNotPremium,
    SlotUnavailable,
    UnknownBooking,
    UnknownMachine,
    UnknownMember,
)
from models import BookingStatus
from store import InMemoryBookingStore

from tests.conftest import at


def test_create_booking_happy_path(service, events):
    b = service.create_booking("treadmill-1", "m-prem", at(10), at(11))
    assert b.status == BookingStatus.ACTIVE
    assert service.bookings(machine_id="treadmill-1") == [b]
    assert [e.type for e in events.events()] == [EventType.BOOKING_CREATED]


def test_unknown_machine(service):
    with pytest.raises(UnknownMachine):
        service.create_booking("treadmill-9", "m-prem", at(10), at(11))


def test_non_reserved_machine_is_rejected(service):
    with pytest.raises(MachineNotReservable):
        service.create_booking("treadmill-3", "m-prem", at(10), at(11))


def test_unknown_member(service):
    with pytest.raises(UnknownMember):
        service.create_booking("treadmill-1", "ghost", at(10), at(11))


def test_non_premium_member_is_rejected(service):
    with pytest.raises(MemberNotPremium):
        service.create_booking("treadmill-1", "m-basic", at(10), at(11))


def test_past_start_is_rejected(service):
    with pytest.raises(InvalidWindow):
        service.create_booking("treadmill-1", "m-prem", at(8), at(9))


def test_duration_bounds(service):
    with pytest.raises(InvalidWindow):
        service.create_booking("treadmill-1", "m-prem", at(10), at(10, 5))  # too short
    with pytest.raises(InvalidWindow):
        service.create_booking("treadmill-1", "m-prem", at(10), at(13))     # too long


def test_naive_datetime_is_rejected(service):
    with pytest.raises(InvalidWindow):
        service.create_booking(
            "treadmill-1", "m-prem", datetime(2026, 9, 2, 10), datetime(2026, 9, 2, 11)
        )


def test_overlap_is_rejected_and_logged(service, events):
    service.create_booking("treadmill-1", "m-prem", at(10), at(11))
    with pytest.raises(SlotUnavailable):
        service.create_booking("treadmill-1", "m-prem2", at(10, 30), at(11, 30))
    rejected = events.events(EventType.BOOKING_REJECTED)
    assert len(rejected) == 1
    assert rejected[0].data["reason"] == "slot_unavailable"


def test_adjacent_bookings_are_allowed(service):
    service.create_booking("treadmill-1", "m-prem", at(10), at(11))
    service.create_booking("treadmill-1", "m-prem2", at(11), at(12))
    assert len(service.bookings(machine_id="treadmill-1")) == 2


def test_cancelled_slot_frees_the_window(service):
    b = service.create_booking("treadmill-1", "m-prem", at(10), at(11))
    service.cancel_booking(b.id)
    again = service.create_booking("treadmill-1", "m-prem2", at(10), at(11))
    assert again.id != b.id


def test_cancel_is_idempotent_and_logs_once(service, events):
    b = service.create_booking("treadmill-1", "m-prem", at(10), at(11))
    service.cancel_booking(b.id)
    service.cancel_booking(b.id)
    assert len(events.events(EventType.BOOKING_CANCELLED)) == 1


def test_cancel_unknown_booking(service):
    with pytest.raises(UnknownBooking):
        service.cancel_booking("nope")


def test_suggest_slot_returns_a_bookable_window(service):
    service.create_booking("treadmill-1", "m-prem", at(9), at(10))
    service.create_booking("treadmill-2", "m-prem2", at(9), at(10, 30))
    s = service.suggest_slot(timedelta(hours=1), earliest_start=at(9))
    # treadmill-1 frees first (10:00 vs 10:30)
    assert (s.machine_id, s.start) == ("treadmill-1", at(10))
    booked = service.create_booking(s.machine_id, "m-prem", s.start, s.end)
    assert booked.start == s.start


def test_service_defaults_work_without_explicit_machines(members):
    svc = BookingService(InMemoryBookingStore(), members=members)
    assert len(svc.machines) == 6
