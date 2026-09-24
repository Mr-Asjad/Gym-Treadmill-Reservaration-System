"""Core data model for the booking service (CLAUDE.md Phase 1).

Plain dataclasses plus the interval math the schedulers share. Nothing here
knows about SQLite, CP-SAT, the CV service, or the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


def utcnow() -> datetime:
    """Timezone-aware 'now'. All datetimes in the system are aware UTC."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Normalise an aware datetime to UTC. Naive datetimes are rejected."""
    if dt.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    return dt.astimezone(timezone.utc)


def intervals_overlap(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    """Half-open overlap test: [a_start, a_end) vs [b_start, b_end).

    Back-to-back intervals (a_end == b_start) do NOT overlap.
    """
    return a_start < b_end and b_start < a_end


class BookingStatus(str, Enum):
    ACTIVE = "active"          # counts against the machine's timeline
    CANCELLED = "cancelled"    # released by the member
    COMPLETED = "completed"    # ran to term
    NO_SHOW = "no_show"        # released after the grace period (Phase 4)


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    is_premium: bool = False   # only premium members may book reserved machines


@dataclass(frozen=True)
class Machine:
    id: str
    name: str
    is_reserved: bool = False  # only reserved machines are bookable at all


@dataclass
class Booking:
    id: str
    machine_id: str
    member_id: str
    start: datetime
    end: datetime
    status: BookingStatus = BookingStatus.ACTIVE
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        self.start = to_utc(self.start)
        self.end = to_utc(self.end)
        self.created_at = to_utc(self.created_at)
        if isinstance(self.status, str):
            self.status = BookingStatus(self.status)
        if self.end <= self.start:
            raise ValueError(f"booking {self.id!r}: end must be after start")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def blocks_timeline(self) -> bool:
        return self.status == BookingStatus.ACTIVE

    def overlaps(self, other: "Booking") -> bool:
        return (
            self.machine_id == other.machine_id
            and self.blocks_timeline()
            and other.blocks_timeline()
            and intervals_overlap(self.start, self.end, other.start, other.end)
        )


@dataclass(frozen=True)
class SlotRequest:
    """A member's wish for a slot of `duration`, no earlier than `earliest_start`.

    `machine_ids=None` means "any reserved machine". This is the unit both the
    simple scheduler and (Phase 5) the CP-SAT scheduler consume.
    """
    member_id: str
    duration: timedelta
    earliest_start: datetime
    machine_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SlotSuggestion:
    machine_id: str
    start: datetime
    end: datetime
    request: SlotRequest | None = None

    @property
    def wait(self) -> timedelta:
        if self.request is None:
            return timedelta(0)
        return self.start - self.request.earliest_start


# The gym: 6 treadmills, the first 2 reserved (CLAUDE.md "Core Product Decisions").
DEFAULT_MACHINES: tuple[Machine, ...] = (
    Machine("treadmill-1", "Treadmill 1", is_reserved=True),
    Machine("treadmill-2", "Treadmill 2", is_reserved=True),
    Machine("treadmill-3", "Treadmill 3"),
    Machine("treadmill-4", "Treadmill 4"),
    Machine("treadmill-5", "Treadmill 5"),
    Machine("treadmill-6", "Treadmill 6"),
)


def reserved_machines(
    machines: "tuple[Machine, ...] | list[Machine]" = DEFAULT_MACHINES,
) -> tuple[Machine, ...]:
    return tuple(m for m in machines if m.is_reserved)
