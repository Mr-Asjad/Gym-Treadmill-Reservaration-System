"""Configuration for the booking service.

All tunable durations and the scheduler mode live here, never hardcoded in logic
(see CLAUDE.md "Conventions"). Every value can be overridden with an env var so
the demo and tests can retune without code changes.
"""
from __future__ import annotations

import os
from datetime import timedelta


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


# "simple" (default) | "cpsat" -- see CLAUDE.md "CP-SAT Toggle".
SCHEDULER_MODE: str = os.environ.get("SCHEDULER_MODE", "simple").strip().lower()
VALID_SCHEDULER_MODES: tuple[str, ...] = ("simple", "cpsat")

# Grace period before an unclaimed booking is released as a no-show (Phase 4).
GRACE_PERIOD: timedelta = timedelta(seconds=_int_env("GRACE_PERIOD_SECONDS", 5 * 60))

# How long before a booking starts we begin nudging a wrong occupant (Phase 4).
NUDGE_WINDOW: timedelta = timedelta(seconds=_int_env("NUDGE_WINDOW_SECONDS", 3 * 60))

# Booking duration bounds.
MIN_BOOKING_DURATION: timedelta = timedelta(
    seconds=_int_env("MIN_BOOKING_DURATION_SECONDS", 10 * 60)
)
MAX_BOOKING_DURATION: timedelta = timedelta(
    seconds=_int_env("MAX_BOOKING_DURATION_SECONDS", 90 * 60)
)

# How far ahead slot suggestion will search for an opening.
SLOT_SEARCH_HORIZON: timedelta = timedelta(
    seconds=_int_env("SLOT_SEARCH_HORIZON_SECONDS", 24 * 3600)
)

# CP-SAT solver time budget for multi-request slot suggestion (Phase 5). The
# model is tiny, so this is only a safety net -- if CP-SAT does not return in
# time the suggestion falls back to the simple scheduler. 0 => no limit.
CPSAT_TIME_LIMIT_SECONDS: float = _float_env("CPSAT_TIME_LIMIT_SECONDS", 5.0)

# Fixed timeslot grid used by the booking UI.
SLOT_MINUTES: int = _int_env("SLOT_MINUTES", 30)
OPEN_HOUR: int = _int_env("OPEN_HOUR", 6)    # gym opens (local time)
CLOSE_HOUR: int = _int_env("CLOSE_HOUR", 22)  # last slot ends by here

# Append-only event log (JSONL). Empty => events are kept in memory only.
EVENT_LOG_PATH: str = os.environ.get("EVENT_LOG_PATH", "")

# Default SQLite path for the booking store (":memory:" for an ephemeral store).
DB_PATH: str = os.environ.get("BOOKING_DB_PATH", "bookings.db")
