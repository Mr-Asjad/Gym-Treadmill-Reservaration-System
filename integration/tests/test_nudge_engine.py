from datetime import datetime, timedelta, timezone

import pytest

from events import EventType
from models import BookingStatus, Member
from service import BookingService
from store import InMemoryBookingStore

from nudge_engine import AdherenceStats, NudgeEngine, adherence_stats

T0 = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
GRACE = timedelta(minutes=5)
NUDGE_WINDOW = timedelta(minutes=3)

MEMBERS = (
    Member("m-ada", "Ada", is_premium=True),
    Member("m-bo", "Bo", is_premium=True),
)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def svc():
    clock = Clock(T0 - timedelta(hours=1))
    return BookingService(InMemoryBookingStore(), members=MEMBERS, clock=clock)


@pytest.fixture
def engine(svc):
    return NudgeEngine(
        svc, clock=Clock(T0), grace_period=GRACE, nudge_window=NUDGE_WINDOW
    )


def book(svc, machine="treadmill-1", member="m-ada", start=T0, minutes=30):
    return svc.create_booking(machine, member, start, start + timedelta(minutes=minutes))


# --------------------------------------------------------------------- no-show

def test_no_show_release_after_grace_when_empty(svc, engine):
    b = book(svc)
    evs = engine.tick({"treadmill-1": False}, T0 + GRACE)
    assert [e.kind for e in evs] == ["no_show_release"]
    assert svc.bookings()[0].status == BookingStatus.NO_SHOW


def test_no_release_before_grace(svc, engine):
    book(svc)
    assert engine.tick({"treadmill-1": False}, T0 + timedelta(minutes=4)) == []


def test_no_release_when_member_showed_up_during_grace(svc, engine):
    b = book(svc)
    engine.tick({"treadmill-1": True}, T0 + timedelta(minutes=1))   # arrived
    evs = engine.tick({"treadmill-1": False}, T0 + timedelta(minutes=10))  # stepped off
    assert evs == []
    assert svc.bookings()[0].status == BookingStatus.ACTIVE


def test_no_show_release_fires_once(svc, engine):
    book(svc)
    engine.tick({"treadmill-1": False}, T0 + GRACE)
    evs = engine.tick({"treadmill-1": False}, T0 + GRACE + timedelta(minutes=1))
    assert evs == []


def test_no_show_needs_cv_data(svc, engine):
    book(svc)
    assert engine.tick({}, T0 + GRACE) == []
    assert svc.bookings()[0].status == BookingStatus.ACTIVE


def test_no_show_release_logs_event(svc, engine):
    book(svc)
    engine.tick({"treadmill-1": False}, T0 + GRACE)
    logged = [e.type for e in svc.events()]
    assert EventType.NO_SHOW_RELEASED in logged


def test_no_action_before_window_starts(svc, engine):
    book(svc, start=T0 + timedelta(hours=2))
    assert engine.tick({"treadmill-1": False}, T0) == []


# ----------------------------------------------------------------------- nudge

def test_nudge_when_occupied_before_start(svc, engine):
    book(svc)
    evs = engine.tick({"treadmill-1": True}, T0 - timedelta(minutes=2))
    assert [e.kind for e in evs] == ["nudge"]
    assert svc.event_log.events(EventType.NUDGE_FIRED)


def test_no_nudge_when_empty_before_start(svc, engine):
    book(svc)
    assert engine.tick({"treadmill-1": False}, T0 - timedelta(minutes=2)) == []


def test_no_nudge_outside_window(svc, engine):
    book(svc)
    assert engine.tick({"treadmill-1": True}, T0 - timedelta(minutes=10)) == []


def test_nudge_fires_once_per_booking(svc, engine):
    book(svc)
    engine.tick({"treadmill-1": True}, T0 - timedelta(minutes=3))
    evs = engine.tick({"treadmill-1": True}, T0 - timedelta(minutes=1))
    assert evs == []


def test_nudge_and_no_show_independent_per_machine(svc, engine):
    book(svc, machine="treadmill-1", member="m-ada")
    book(svc, machine="treadmill-2", member="m-bo")
    evs = engine.tick(
        {"treadmill-1": True, "treadmill-2": False}, T0 - timedelta(minutes=2)
    )
    assert [(e.kind, e.machine_id) for e in evs] == [("nudge", "treadmill-1")]


# ------------------------------------------------------------------- adherence

def test_adherence_counts_no_shows_against_rate(svc, engine):
    book(svc, machine="treadmill-1", member="m-ada")
    book(svc, machine="treadmill-2", member="m-bo")
    engine.tick({"treadmill-1": True, "treadmill-2": False}, T0 + timedelta(minutes=1))
    engine.tick({"treadmill-1": True, "treadmill-2": False}, T0 + GRACE)

    stats = adherence_stats(svc, T0 + timedelta(hours=1))
    assert stats == AdherenceStats(total=2, honored=1, no_shows=1, cancelled=0)
    assert stats.adherence_pct == 50.0


def test_prime_from_events_suppresses_refired_nudge_and_no_show(svc):
    b1 = book(svc, machine="treadmill-1", member="m-ada")
    b2 = book(svc, machine="treadmill-2", member="m-bo")

    fresh = NudgeEngine(
        svc, clock=Clock(T0), grace_period=GRACE, nudge_window=NUDGE_WINDOW
    )
    fresh.prime_from_events([
        {"type": "nudge_fired", "data": {"booking_id": b1.id}},
        {"type": "no_show_released", "data": {"booking_id": b2.id}},
    ])
    # b1 already nudged, b2 already released -> nothing re-fires
    assert fresh.tick({"treadmill-1": True}, T0 - timedelta(minutes=2)) == []
    assert fresh.tick({"treadmill-2": False}, T0 + GRACE) == []


def test_adherence_ignores_future_and_cancelled(svc):
    past = book(svc, start=T0)
    book(svc, machine="treadmill-2", start=T0 + timedelta(hours=3))
    svc.cancel_booking(past.id)
    stats = adherence_stats(svc, T0 + timedelta(minutes=45))
    assert stats.total == 0
    assert stats.cancelled == 1
    assert stats.adherence_pct == 100.0
