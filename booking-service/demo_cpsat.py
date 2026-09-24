"""Phase 5 demo: the same batch of pending requests, simple vs CP-SAT mode.

    pip install ortools
    python demo_cpsat.py

Shows a case where assigning requests greedily in arrival order costs an extra
hour of total member wait, and CP-SAT removes it -- same interface, one config
switch (SCHEDULER_MODE).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models import SlotRequest
from scheduler import SimpleScheduler

NOW = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)


def total_wait(suggestions, requests) -> timedelta:
    return sum(
        (s.start - r.earliest_start for s, r in zip(suggestions, requests)),
        timedelta(),
    )


def show(label, scheduler, requests) -> None:
    out = scheduler.suggest(requests, [])
    print(f"\n{label}")
    for r, s in zip(requests, out):
        print(
            f"  {r.member_id}: {r.duration} from {r.earliest_start:%H:%M}"
            f"  ->  {s.machine_id} {s.start:%H:%M}-{s.end:%H:%M}"
            f"  (wait {s.start - r.earliest_start})"
        )
    print(f"  total wait: {total_wait(out, requests)}")


def main() -> None:
    requests = [
        SlotRequest("m-ada", timedelta(hours=1), NOW),
        SlotRequest("m-bo", timedelta(minutes=30), NOW, machine_ids=("treadmill-1",)),
    ]

    show("SCHEDULER_MODE=simple (greedy, in arrival order)", SimpleScheduler(), requests)

    try:
        from cpsat_scheduler import CpSatScheduler
    except ImportError:
        print("\nSCHEDULER_MODE=cpsat: install `ortools` to run this half")
        return
    show("SCHEDULER_MODE=cpsat (minimise total wait)", CpSatScheduler(), requests)


if __name__ == "__main__":
    main()
