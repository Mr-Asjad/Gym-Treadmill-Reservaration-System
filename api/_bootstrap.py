"""Put `booking-service/` and `integration/` on sys.path and name the shared
data files. The API wraps the booking service and the Phase 4 nudge engine; it
does not import the CV service (consumed only through the zone-state JSONL, same
as integration/_bootstrap.py -- the two `config` modules cannot coexist)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

for name in ("integration", "booking-service"):
    p = str(ROOT / name)
    if p not in sys.path:
        sys.path.insert(0, p)

DB_PATH = str(DATA_DIR / "bookings.db")
EVENT_LOG_PATH = str(DATA_DIR / "events.jsonl")
STATE_LOG_PATH = str(DATA_DIR / "zone_states.jsonl")
WEB_DIST = ROOT / "web" / "dist"
