"""The member booking grid: fixed 30-minute slots x the 2 reserved treadmills,
each cell tagged open / booked / mine / past. Grid shape (slot length, open and
close hours) comes from booking-service config; times are gym-local."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Callable

import config
from models import to_utc

SLOT = timedelta(minutes=config.SLOT_MINUTES)


def gym_tz():
    return datetime.now().astimezone().tzinfo


def day_slot_starts(day: date, tz) -> list[datetime]:
    opens = datetime.combine(day, time(config.OPEN_HOUR), tzinfo=tz)
    closes = datetime.combine(day, time(config.CLOSE_HOUR), tzinfo=tz)
    out, t = [], opens
    while t + SLOT <= closes:
        out.append(t)
        t += SLOT
    return out


def _covering(bookings, slot_start_utc: datetime):
    for b in bookings:
        if b.start <= slot_start_utc < b.end:
            return b
    return None


def slot_grid(
    svc,
    day: date,
    member_id: "str | None",
    now: datetime,
    tz,
    *,
    member_name: Callable[[str], str],
) -> list[dict]:
    machines = [m for m in svc.machines if m.is_reserved]
    active = {m.id: svc.bookings(machine_id=m.id, active_only=True) for m in machines}

    rows: list[dict] = []
    for slot in day_slot_starts(day, tz):
        slot_utc = to_utc(slot)
        if slot_utc + SLOT <= now:
            continue  # slot already finished -- don't show a wall of dead rows
        cells = []
        for m in machines:
            b = _covering(active[m.id], slot_utc)
            if b is not None:
                mine = b.member_id == member_id
                cells.append({
                    "machine_id": m.id,
                    "state": "mine" if mine else "booked",
                    "booking_id": b.id,
                    "member_name": member_name(b.member_id),
                })
            elif slot_utc < now:
                cells.append({"machine_id": m.id, "state": "past", "booking_id": None,
                              "member_name": None})
            else:
                cells.append({"machine_id": m.id, "state": "open", "booking_id": None,
                              "member_name": None})
        rows.append({
            "label": slot.strftime("%H:%M"),
            "start": slot_utc.isoformat(),
            "cells": cells,
        })
    return rows
