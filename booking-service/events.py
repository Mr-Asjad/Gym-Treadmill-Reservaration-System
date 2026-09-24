"""Append-only event log.

Every booking / rejection / no-show / nudge is recorded with a timestamp. This
is the trail behind the "schedule adherence %" demo metric and a debugging log
during development (CLAUDE.md "Conventions").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from models import utcnow


class EventType(str, Enum):
    BOOKING_CREATED = "booking_created"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_REJECTED = "booking_rejected"
    NO_SHOW_RELEASED = "no_show_released"   # Phase 4
    NUDGE_FIRED = "nudge_fired"             # Phase 4


@dataclass(frozen=True)
class Event:
    type: EventType
    at: datetime
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type.value, "at": self.at.isoformat(), "data": self.data}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventLog:
    """In-memory list of events, optionally mirrored to a JSONL file."""

    def __init__(self, path: "str | Path | None" = None) -> None:
        self._path = Path(path) if path else None
        self._events: list[Event] = []
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, type: EventType, **data: Any) -> Event:
        event = Event(type=type, at=utcnow(), data=data)
        self._events.append(event)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(event.to_json() + "\n")
        return event

    def events(self, type: "EventType | None" = None) -> list[Event]:
        if type is None:
            return list(self._events)
        return [e for e in self._events if e.type == type]

    def __len__(self) -> int:
        return len(self._events)
