"""Phase 4 smoke demo -- the closed loop, no camera, no model weights.

    python demo.py

The booking service and a scripted occupancy feed meet in the nudge engine:

  1. Ada books Reserved Treadmill 1 for 09:00-09:30; Bo books Treadmill 2.
  2. 08:58 -- someone is already on Treadmill 1  -> soft nudge fires.
  3. That person leaves; Ada never arrives.
  4. 09:05 -- Treadmill 1 still empty, grace period passed -> no-show release.
  5. Bo is on Treadmill 2 through the window -> his booking stays honored.

Ends with the schedule-adherence metric (1 of 2 concluded bookings honored).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import _bootstrap  # noqa: F401  -- puts booking-service on sys.path

from members import DEFAULT_MEMBERS
from service import BookingService
from store import InMemoryBookingStore

from nudge_engine import NudgeEngine, adherence_stats

T0 = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
GRACE = timedelta(minutes=5)
NUDGE_WINDOW = timedelta(minutes=3)


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def main() -> None:
    clock = Clock(T0 - timedelta(hours=1))
    svc = BookingService(
        InMemoryBookingStore(), members=DEFAULT_MEMBERS, clock=clock
    )
    ada = svc.create_booking("treadmill-1", "m-ada", T0, T0 + timedelta(minutes=30))
    bo = svc.create_booking("treadmill-2", "m-bo", T0, T0 + timedelta(minutes=30))
    print(f"booked  treadmill-1 09:00-09:30  {ada.member_id} (Ada)")
    print(f"booked  treadmill-2 09:00-09:30  {bo.member_id} (Bo)\n")

    engine = NudgeEngine(
        svc, clock=clock, grace_period=GRACE, nudge_window=NUDGE_WINDOW
    )

    timeline = [
        (T0 - timedelta(minutes=2), {"treadmill-1": True, "treadmill-2": False}),
        (T0,                        {"treadmill-1": False, "treadmill-2": True}),
        (T0 + timedelta(minutes=3), {"treadmill-1": False, "treadmill-2": True}),
        (T0 + timedelta(minutes=6), {"treadmill-1": False, "treadmill-2": True}),
        (T0 + timedelta(minutes=30), {"treadmill-1": False, "treadmill-2": False}),
    ]

    for now, occupancy in timeline:
        clock.t = now
        for ev in engine.tick(occupancy, now):
            print(f"  {now:%H:%M}  {ev.kind:<16}  {ev.machine_id}  ({ev.detail})")

    clock.t = T0 + timedelta(minutes=31)
    stats = adherence_stats(svc, clock())
    print(f"\nbooking states:")
    for b in svc.bookings():
        print(f"  {b.machine_id}  {b.member_id}  {b.status.value}")
    print(
        f"\nschedule adherence: {stats.adherence_pct:.0f}%  "
        f"({stats.honored}/{stats.total} concluded bookings honored, "
        f"{stats.no_shows} no-show)"
    )


if __name__ == "__main__":
    main()
