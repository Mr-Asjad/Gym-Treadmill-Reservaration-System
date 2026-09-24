"""Pure logic that turns (booking, camera occupancy, clock) into a per-machine
verdict, plus a reader for the shared event log.

No web framework here -- these rules are unit-tested on their own (moved from the
old Streamlit dashboard, where they already had coverage).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

# machine-readable verdicts (the frontend maps these to colour / label)
IDLE = "idle"
UNBOOKED_USE = "unbooked_use"
RESERVED_SOON = "reserved_soon"
NUDGE = "nudge"
ON_MACHINE = "on_machine"
WAITING = "waiting"
NO_SHOW = "no_show"
NO_CAMERA = "no_camera"


@dataclass(frozen=True)
class MachineView:
    machine_id: str
    machine_name: str
    member_name: "str | None"
    window: "tuple[datetime, datetime] | None"
    occupied: "bool | None"
    occupied_since: "datetime | None"
    verdict: str
    headline: str


def pick_booking(bookings: Sequence, now: datetime):
    """The booking that matters right now: the active one whose window has not
    ended yet, earliest first. `bookings` should already be filtered to one
    machine and active-only."""
    upcoming = [b for b in bookings if b.end > now]
    return min(upcoming, key=lambda b: b.start) if upcoming else None


def _mmss(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    return f"{total // 60}m{total % 60:02d}s"


def machine_view(
    machine,
    booking,
    member_name: "str | None",
    occupied: "bool | None",
    occupied_since: "datetime | None",
    now: datetime,
    *,
    grace: timedelta,
    nudge_window: timedelta,
) -> MachineView:
    window = (booking.start, booking.end) if booking is not None else None
    who = member_name or (booking.member_id if booking is not None else None)

    def out(verdict: str, headline: str) -> MachineView:
        return MachineView(
            machine.id, machine.name, member_name, window,
            occupied, occupied_since, verdict, headline,
        )

    if occupied is None:
        # camera silent -- still surface the reservation for staff
        if booking is not None and now < booking.start:
            return out(RESERVED_SOON, f"reserved by {who}")
        if booking is not None and now < booking.end:
            return out(NO_CAMERA, f"{who}'s slot, camera offline")
        return out(NO_CAMERA, "no camera signal")

    if booking is None:
        return out(UNBOOKED_USE, "in use, no reservation") if occupied else out(IDLE, "open")

    if now < booking.start:
        if occupied and booking.start - now <= nudge_window:
            return out(
                NUDGE,
                f"occupant present, {who}'s reservation starts in "
                f"{_mmss(booking.start - now)}",
            )
        return out(RESERVED_SOON, f"reserved by {who}")

    if now < booking.end:
        if occupied:
            return out(ON_MACHINE, f"{who} running")
        grace_left = grace - (now - booking.start)
        if grace_left > timedelta(0):
            return out(WAITING, f"waiting for {who}, {_mmss(grace_left)} grace left")
        return out(NO_SHOW, f"{who} no-show, slot released")

    return out(IDLE, "open")


def read_events(path: "str | Path", limit: "int | None" = None) -> list[dict]:
    """The shared JSONL event log, oldest first. `EventLog` only mirrors events
    to this file (it never reads it back), so cross-process history -- a booking
    made in the member UI, say -- is only visible by reading the file."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows[-limit:] if limit else rows
