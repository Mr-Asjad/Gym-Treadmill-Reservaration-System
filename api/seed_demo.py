"""Seed the shared store for a demo run of the web app.

    python seed_demo.py             # Ada books Reserved Treadmill 1, starting soon
    python seed_demo.py --start 30  # ...starting 30s from now
    python seed_demo.py --reset     # wipe the demo data files first

Then run the API with short windows so the loop fits a short video:

    GRACE_PERIOD_SECONDS=30 NUDGE_WINDOW_SECONDS=60 uvicorn main:app

Demo beats on the Floor view: card reads "reserved" -> flip the machine's
"someone on it" toggle before the start -> NUDGE + toast -> flip off, wait out
the grace period -> NO-SHOW released -> adherence drops.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _bootstrap  # noqa: F401
from service import build_service

FILES = ("bookings.db", "events.jsonl", "zone_states.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=90,
                    help="seconds from now the reservation starts (default 90)")
    ap.add_argument("--minutes", type=int, default=30, help="reservation length")
    ap.add_argument("--machine", default="treadmill-1")
    ap.add_argument("--member", default="m-ada")
    ap.add_argument("--reset", action="store_true",
                    help="delete the demo data files before seeding")
    args = ap.parse_args()

    data_dir = Path(_bootstrap.DATA_DIR)
    if args.reset:
        for name in FILES:
            f = data_dir / name
            if f.exists():
                f.unlink()
                print(f"removed {f}")

    svc = build_service(
        db_path=_bootstrap.DB_PATH, event_log_path=_bootstrap.EVENT_LOG_PATH
    )
    start = datetime.now(timezone.utc) + timedelta(seconds=args.start)
    end = start + timedelta(minutes=args.minutes)
    b = svc.create_booking(args.machine, args.member, start, end)
    print(
        f"booked {b.machine_id} for {b.member_id}: "
        f"{start.astimezone():%H:%M:%S}-{end.astimezone():%H:%M:%S} "
        f"(starts in {args.start}s)"
    )


if __name__ == "__main__":
    main()
