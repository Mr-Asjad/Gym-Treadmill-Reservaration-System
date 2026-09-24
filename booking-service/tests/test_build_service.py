from datetime import datetime, timedelta, timezone

import pytest

from members import DEFAULT_MEMBERS, member_by_id
from service import MemberNotPremium, build_service


def test_roster_has_premium_and_basic_members():
    assert any(m.is_premium for m in DEFAULT_MEMBERS)
    assert any(not m.is_premium for m in DEFAULT_MEMBERS)
    assert member_by_id("m-ada").is_premium
    assert member_by_id("nope") is None


def test_build_service_persists_across_instances(tmp_path):
    db = str(tmp_path / "b.db")
    log = str(tmp_path / "events.jsonl")
    clock = lambda: datetime(2026, 9, 2, 9, tzinfo=timezone.utc)

    svc = build_service(db_path=db, event_log_path=log, clock=clock)
    start = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
    booking = svc.create_booking("treadmill-1", "m-ada", start, start + timedelta(hours=1))

    reopened = build_service(db_path=db, event_log_path=log, clock=clock)
    assert [b.id for b in reopened.bookings()] == [booking.id]
    assert (tmp_path / "events.jsonl").exists()


def test_build_service_enforces_premium(tmp_path):
    svc = build_service(
        db_path=str(tmp_path / "b.db"),
        event_log_path=str(tmp_path / "e.jsonl"),
        clock=lambda: datetime(2026, 9, 2, 9, tzinfo=timezone.utc),
    )
    start = datetime(2026, 9, 2, 10, tzinfo=timezone.utc)
    with pytest.raises(MemberNotPremium):
        svc.create_booking("treadmill-1", "m-cy", start, start + timedelta(hours=1))
