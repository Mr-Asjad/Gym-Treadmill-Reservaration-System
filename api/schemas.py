"""Response / request shapes for the API. Pydantic so the OpenAPI schema at
/docs is accurate and the TS client can be kept honest by hand."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Member(BaseModel):
    id: str
    name: str
    is_premium: bool


class Machine(BaseModel):
    id: str
    name: str


class BookingOut(BaseModel):
    id: str
    machine_id: str
    member_id: str
    member_name: str
    start: datetime
    end: datetime
    status: str


class SlotCell(BaseModel):
    machine_id: str
    state: str  # open | booked | mine | past
    booking_id: str | None = None
    member_name: str | None = None


class SlotRow(BaseModel):
    label: str
    start: datetime
    cells: list[SlotCell]


class CreateBooking(BaseModel):
    machine_id: str
    member_id: str
    start: datetime
    end: datetime


class SuggestRequest(BaseModel):
    member_id: str
    duration_minutes: int = 30
    earliest: datetime | None = None


class Suggestion(BaseModel):
    machine_id: str
    start: datetime
    end: datetime
    wait_seconds: float


class CameraState(BaseModel):
    occupied: bool | None = None
    since: datetime | None = None


class FloorMachine(BaseModel):
    machine_id: str
    machine_name: str
    member_name: str | None
    window: list[datetime] | None
    camera: CameraState
    verdict: str
    headline: str


class Adherence(BaseModel):
    total: int
    honored: int
    no_shows: int
    cancelled: int
    adherence_pct: float


class FiredEvent(BaseModel):
    kind: str
    machine_id: str
    member_name: str
    detail: str


class FloorState(BaseModel):
    now: datetime
    scheduler_mode: str
    machines: list[FloorMachine]
    adherence: Adherence
    fired: list[FiredEvent]


class ActivityEvent(BaseModel):
    at: datetime
    type: str
    label: str
    machine_id: str | None = None
    member_name: str | None = None


class SimOccupancy(BaseModel):
    machine_id: str
    occupied: bool
