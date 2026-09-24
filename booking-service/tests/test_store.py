from datetime import datetime, timezone

import pytest

from models import Booking, BookingStatus
from store import InMemoryBookingStore, SQLiteBookingStore


def make_booking(bid="b1", machine="treadmill-1", start_h=10, end_h=11):
    return Booking(
        id=bid,
        machine_id=machine,
        member_id="m",
        start=datetime(2026, 9, 2, start_h, tzinfo=timezone.utc),
        end=datetime(2026, 9, 2, end_h, tzinfo=timezone.utc),
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request):
    if request.param == "memory":
        yield InMemoryBookingStore()
    else:
        s = SQLiteBookingStore(":memory:")
        yield s
        s.close()


def test_add_get_roundtrip(store):
    b = make_booking()
    store.add(b)
    got = store.get("b1")
    assert got is not None
    assert got.machine_id == "treadmill-1"
    assert got.start == b.start
    assert got.start.tzinfo is not None


def test_duplicate_id_rejected(store):
    store.add(make_booking())
    with pytest.raises(KeyError):
        store.add(make_booking())


def test_update_status_persists(store):
    b = make_booking()
    store.add(b)
    b.status = BookingStatus.CANCELLED
    store.update(b)
    assert store.get("b1").status == BookingStatus.CANCELLED


def test_update_unknown_rejected(store):
    with pytest.raises(KeyError):
        store.update(make_booking())


def test_all_and_for_machine(store):
    store.add(make_booking("b1", "treadmill-1", 10, 11))
    store.add(make_booking("b2", "treadmill-2", 9, 10))
    store.add(make_booking("b3", "treadmill-1", 12, 13))
    assert [b.id for b in store.all()] == ["b2", "b1", "b3"]  # ordered by start
    assert {b.id for b in store.for_machine("treadmill-1")} == {"b1", "b3"}


def test_get_missing_returns_none(store):
    assert store.get("nope") is None
