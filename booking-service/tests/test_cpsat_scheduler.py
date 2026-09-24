from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("ortools")  # CP-SAT mode is optional (CLAUDE.md "CP-SAT Toggle")

from cpsat_scheduler import CpSatScheduler
from models import Booking, BookingStatus, SlotRequest
from scheduler import SimpleScheduler, build_scheduler

HOUR = timedelta(hours=1)


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


def total_wait(suggestions, requests):
    return sum(
        (s.start - r.earliest_start for s, r in zip(suggestions, requests)),
        timedelta(),
    )


@pytest.fixture
def cpsat():
    return CpSatScheduler()


# ------------------------------------------------------------- interface parity

def test_build_scheduler_returns_cpsat():
    assert isinstance(build_scheduler("cpsat"), CpSatScheduler)


def test_is_available_matches_simple(cpsat):
    existing = [booking("treadmill-1", 9, 10)]
    assert not cpsat.is_available("treadmill-1", at(9, 30), at(10, 30), existing)
    assert cpsat.is_available("treadmill-1", at(10), at(11), existing)
    assert cpsat.is_available("treadmill-2", at(9), at(10), existing)


def test_is_available_can_ignore_a_booking(cpsat):
    b = booking("treadmill-1", 9, 10)
    assert cpsat.is_available(
        "treadmill-1", at(9), at(10), [b], ignore_booking_id=b.id
    )


def test_single_request_delegates_to_greedy(cpsat):
    existing = [booking("treadmill-1", 9, 12)]
    [s] = cpsat.suggest([SlotRequest("m", HOUR, at(9))], existing)
    assert s.machine_id == "treadmill-2"
    assert s.start == at(9)


# ---------------------------------------------------------------- optimisation

def test_cpsat_beats_greedy_when_constrained_request_is_second(cpsat):
    """Greedy gives R1 the only unconstrained-optimal slot on treadmill-1, then
    R2 (locked to treadmill-1) has to wait an hour. CP-SAT puts R1 on treadmill-2
    and both start on time."""
    reqs = [
        SlotRequest("a", HOUR, at(9)),
        SlotRequest("b", timedelta(minutes=30), at(9), machine_ids=("treadmill-1",)),
    ]

    greedy = SimpleScheduler().suggest(reqs, [])
    assert total_wait(greedy, reqs) == HOUR  # greedy is suboptimal here

    out = cpsat.suggest(reqs, [])
    assert total_wait(out, reqs) == timedelta(0)
    assert out[1].machine_id == "treadmill-1"  # b keeps its only option
    assert out[0].machine_id == "treadmill-2"  # a yields


def test_cpsat_output_is_a_valid_non_overlapping_schedule(cpsat):
    existing = [booking("treadmill-1", 9, 11)]
    reqs = [SlotRequest(x, HOUR, at(9)) for x in ("a", "b", "c")]

    out = cpsat.suggest(reqs, existing)

    assert len(out) == 3
    for s, r in zip(out, reqs):
        assert s.start >= r.earliest_start
        assert s.end - s.start == r.duration
        assert cpsat.is_available(s.machine_id, s.start, s.end, existing)

    by_machine: dict[str, list] = {}
    for s in out:
        by_machine.setdefault(s.machine_id, []).append((s.start, s.end))
    for intervals in by_machine.values():
        intervals.sort()
        for (_, e1), (s2, _) in zip(intervals, intervals[1:]):
            assert e1 <= s2


def test_cpsat_never_worse_than_greedy(cpsat):
    existing = [booking("treadmill-2", 9, 10)]
    reqs = [
        SlotRequest("a", HOUR, at(9)),
        SlotRequest("b", timedelta(minutes=30), at(9)),
        SlotRequest("c", HOUR, at(10), machine_ids=("treadmill-1",)),
    ]
    greedy = SimpleScheduler().suggest(reqs, existing)
    out = cpsat.suggest(reqs, existing)
    assert total_wait(out, reqs) <= total_wait(greedy, reqs)


def test_respects_earliest_start(cpsat):
    reqs = [
        SlotRequest("a", HOUR, at(14)),
        SlotRequest("b", HOUR, at(9)),
    ]
    out = cpsat.suggest(reqs, [])
    assert out[0].start >= at(14)
    assert out[1].start >= at(9)
