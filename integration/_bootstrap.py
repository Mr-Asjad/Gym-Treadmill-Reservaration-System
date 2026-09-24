"""Make `booking-service/` importable and define shared data paths.

The nudge engine is the one place the booking service and the CV service meet
(CLAUDE.md "Architecture"). It imports the booking service directly; the CV
service is consumed only through its data contract (`ZoneStateChange` records),
so it is *not* put on the path here -- both services define a top-level `config`
module and cannot share one interpreter's import namespace.

Booking state (SQLite + event log) lives in a top-level `data/` dir so the UI,
dashboard, and nudge engine all read the same store.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKING_SERVICE_DIR = ROOT / "booking-service"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

if str(BOOKING_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(BOOKING_SERVICE_DIR))

DB_PATH = str(DATA_DIR / "bookings.db")
EVENT_LOG_PATH = str(DATA_DIR / "events.jsonl")
STATE_LOG_PATH = str(DATA_DIR / "zone_states.jsonl")  # written by cv-service/run.py --json-out
