from datetime import datetime, timedelta, timezone

import pytest

from models import Booking, BookingStatus, SlotRequest
from scheduler import SimpleScheduler, build_scheduler


def at(hour, minute=0):
    return datetime(2026, 9, 2, hour, minute, tzinfo=timezone.utc)


def booking(machine, start_h, end_h, status=BookingStatus.ACTIVE):
    return Booking(
        id=f"{machine}-{start_h}-{end_h}",
        machine_id=machine,
        member_id="m",
        start=at(start_h),
        end=at(end_h),
        status=status,
    )


HOUR = timedelta(hours=1)


@pytest.fixture
def sched():
    return SimpleScheduler()


def test_is_available_on_empty_timeline(sched):
    assert sched.is_available("treadmill-1", at(9), at(10), [])


def test_is_available_detects_overlap_and_allows_adjacent(sched):
    existing = [booking("treadmill-1", 9, 10)]
    assert not sched.is_available("treadmill-1", at(9, 30), at(10, 30), existing)
    assert sched.is_available("treadmill-1", at(10), at(11), existing)
    assert sched.is_available("treadmill-2", at(9), at(10), existing)


def test_is_available_ignores_cancelled(sched):
    existing = [booking("treadmill-1", 9, 10, status=BookingStatus.CANCELLED)]
    assert sched.is_available("treadmill-1", at(9), at(10), existing)


def test_is_available_can_ignore_a_booking_id(sched):
    b = booking("treadmill-1", 9, 10)
    assert sched.is_available(
        "treadmill-1", at(9), at(10), [b], ignore_booking_id=b.id
    )


def test_suggest_picks_earliest_start_on_empty_gym(sched):
    req = SlotRequest("m", HOUR, at(9))
    [s] = sched.suggest([req], [])
    assert (s.machine_id, s.start, s.end) == ("treadmill-1", at(9), at(10))
    assert s.wait == timedelta(0)


def test_suggest_moves_to_second_machine_when_first_is_busy(sched):
    existing = [booking("treadmill-1", 9, 12)]
    [s] = sched.suggest([SlotRequest("m", HOUR, at(9))], existing)
    assert s.machine_id == "treadmill-2"
    assert s.start == at(9)


def test_suggest_finds_earliest_gap(sched):
    existing = [booking("treadmill-1", 9, 10), booking("treadmill-1", 11, 12)]
    # 30 min fits in the 10:00-11:00 gap
    [s] = sched.suggest(
        [SlotRequest("m", timedelta(minutes=30), at(10), machine_ids=("treadmill-1",))],
        existing,
    )
    assert (s.start, s.end) == (at(10), at(10, 30))
    # 90 min does not fit that gap -> after the 11:00-12:00 booking
    [s2] = sched.suggest(
        [SlotRequest("m", timedelta(minutes=90), at(10), machine_ids=("treadmill-1",))],
        existing,
    )
    assert s2.start == at(12)


def test_suggest_batch_keeps_requests_non_overlapping(sched):
    reqs = [SlotRequest("a", HOUR, at(9)), SlotRequest("b", HOUR, at(9))]
    out = sched.suggest(reqs, [])
    # both want 09:00; greedy spreads them across the two reserved machines
    assert {s.machine_id for s in out} == {"treadmill-1", "treadmill-2"}
    assert all(s.start == at(9) for s in out)


def test_suggest_batch_stacks_third_request(sched):
    reqs = [SlotRequest(x, HOUR, at(9)) for x in ("a", "b", "c")]
    out = sched.suggest(reqs, [])
    assert sorted(s.start for s in out) == [at(9), at(9), at(10)]


def test_build_scheduler_defaults_to_simple():
    assert isinstance(build_scheduler("simple"), SimpleScheduler)


def test_build_scheduler_rejects_unknown_mode():
    with pytest.raises(ValueError):
        build_scheduler("banana")
