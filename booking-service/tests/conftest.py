"""Shared fixtures for the booking-service tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from models import DEFAULT_MACHINES, Member
from events import EventLog
from service import BookingService
from store import InMemoryBookingStore

# A fixed "now" so tests never race the wall clock.
NOW = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 2, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def clock():
    return lambda: NOW


@pytest.fixture
def members():
    return [
        Member("m-prem", "Prem Ada", is_premium=True),
        Member("m-prem2", "Prem Bo", is_premium=True),
        Member("m-basic", "Basic Cy", is_premium=False),
    ]


@pytest.fixture
def events():
    return EventLog()


@pytest.fixture
def service(clock, members, events):
    return BookingService(
        InMemoryBookingStore(),
        events=events,
        machines=DEFAULT_MACHINES,
        members=members,
        clock=clock,
    )
