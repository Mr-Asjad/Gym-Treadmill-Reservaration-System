"""Phase 1 smoke demo: book -> reject overlap -> suggest next slot -> cancel.

    python demo.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models import DEFAULT_MACHINES, Member
from service import BookingService, SlotUnavailable
from store import InMemoryBookingStore

NOW = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)


def main() -> None:
    members = [
        Member("m-ada", "Ada", is_premium=True),
        Member("m-bo", "Bo", is_premium=True),
    ]
    svc = BookingService(
        InMemoryBookingStore(),
        machines=DEFAULT_MACHINES,
        members=members,
        clock=lambda: NOW,
    )

    b1 = svc.create_booking("treadmill-1", "m-ada", NOW + timedelta(hours=1),
                            NOW + timedelta(hours=2))
    print(f"booked   {b1.machine_id} {b1.start:%H:%M}-{b1.end:%H:%M} for {b1.member_id}")

    try:
        svc.create_booking("treadmill-1", "m-bo", NOW + timedelta(hours=1, minutes=30),
                           NOW + timedelta(hours=2, minutes=30))
    except SlotUnavailable:
        print("rejected treadmill-1 10:30-11:30 (overlaps existing booking)")

    s = svc.suggest_slot(timedelta(hours=1), earliest_start=NOW + timedelta(hours=1))
    print(f"suggest  earliest 1h slot -> {s.machine_id} {s.start:%H:%M}-{s.end:%H:%M}")
    b2 = svc.create_booking(s.machine_id, "m-bo", s.start, s.end)
    print(f"booked   {b2.machine_id} {b2.start:%H:%M}-{b2.end:%H:%M} for {b2.member_id}")

    svc.cancel_booking(b1.id)
    print(f"cancelled {b1.id}")

    print("\nevents:")
    for e in svc.events():
        print(f"  {e.at:%H:%M:%S}  {e.type.value}  {e.data}")


if __name__ == "__main__":
    main()
