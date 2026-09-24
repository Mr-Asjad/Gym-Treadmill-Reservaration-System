"""BookingService -- the public API for Phase 1.

Rules enforced when a booking is created:
  * the machine exists and is reservable (only the 2 reserved treadmills)
  * the member exists and is premium
  * the window is timezone-aware, well-formed, and within the duration bounds
  * the start is not in the past
  * the window does not overlap an existing active booking on that machine

Every accepted booking, cancellation, and rejection is written to the event log.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Callable, Iterable, Sequence

import config
from events import EventLog, EventType
from models import (
    DEFAULT_MACHINES,
    Booking,
    BookingStatus,
    Machine,
    Member,
    SlotRequest,
    SlotSuggestion,
    to_utc,
    utcnow,
)
from scheduler import Scheduler, build_scheduler
from store import BookingStore


class BookingError(Exception):
    """A booking request was rejected. `code` is the machine-readable reason."""

    code = "booking_error"


class UnknownMachine(BookingError):
    code = "unknown_machine"


class MachineNotReservable(BookingError):
    code = "machine_not_reservable"


class UnknownMember(BookingError):
    code = "unknown_member"


class MemberNotPremium(BookingError):
    code = "member_not_premium"


class InvalidWindow(BookingError):
    code = "invalid_window"


class SlotUnavailable(BookingError):
    code = "slot_unavailable"


class UnknownBooking(BookingError):
    code = "unknown_booking"


def _new_id() -> str:
    return uuid.uuid4().hex


class BookingService:
    def __init__(
        self,
        store: BookingStore,
        *,
        events: "EventLog | None" = None,
        machines: "Sequence[Machine] | None" = None,
        members: Iterable[Member] = (),
        scheduler: "Scheduler | None" = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        # `events or ...` would misfire: an empty EventLog is falsy (__len__ == 0).
        self._events = events if events is not None else EventLog(config.EVENT_LOG_PATH or None)
        machine_seq = tuple(machines) if machines is not None else DEFAULT_MACHINES
        self._machines: dict[str, Machine] = {m.id: m for m in machine_seq}
        self._members: dict[str, Member] = {m.id: m for m in members}
        self._scheduler = (
            scheduler if scheduler is not None else build_scheduler(machines=machine_seq)
        )
        self._clock = clock

    # ------------------------------------------------------------------ reads
    @property
    def machines(self) -> list[Machine]:
        return list(self._machines.values())

    def add_member(self, member: Member) -> None:
        self._members[member.id] = member

    def bookings(
        self,
        *,
        machine_id: "str | None" = None,
        member_id: "str | None" = None,
        active_only: bool = False,
    ) -> list[Booking]:
        out = self._store.all()
        if machine_id is not None:
            out = [b for b in out if b.machine_id == machine_id]
        if member_id is not None:
            out = [b for b in out if b.member_id == member_id]
        if active_only:
            out = [b for b in out if b.status == BookingStatus.ACTIVE]
        return sorted(out, key=lambda b: b.start)

    def events(self) -> list:
        return self._events.events()

    @property
    def event_log(self) -> EventLog:
        """The shared event log. Phase 4's nudge engine appends nudge events here
        so booking and adherence events share one timestamped trail."""
        return self._events

    # ----------------------------------------------------------------- writes
    def create_booking(
        self, machine_id: str, member_id: str, start: datetime, end: datetime
    ) -> Booking:
        try:
            start_utc, end_utc = self._validate(machine_id, member_id, start, end)
        except BookingError as exc:
            self._events.record(
                EventType.BOOKING_REJECTED,
                machine_id=machine_id,
                member_id=member_id,
                reason=exc.code,
            )
            raise

        booking = Booking(
            id=_new_id(),
            machine_id=machine_id,
            member_id=member_id,
            start=start_utc,
            end=end_utc,
        )
        self._store.add(booking)
        self._events.record(
            EventType.BOOKING_CREATED,
            booking_id=booking.id,
            machine_id=machine_id,
            member_id=member_id,
            start=booking.start.isoformat(),
            end=booking.end.isoformat(),
        )
        return booking

    def cancel_booking(self, booking_id: str) -> Booking:
        booking = self._store.get(booking_id)
        if booking is None:
            raise UnknownBooking(booking_id)
        if booking.status != BookingStatus.ACTIVE:
            return booking
        booking.status = BookingStatus.CANCELLED
        self._store.update(booking)
        self._events.record(EventType.BOOKING_CANCELLED, booking_id=booking_id)
        return booking

    def release_no_show(self, booking_id: str) -> Booking:
        """Release an unclaimed booking after the grace period (Phase 4). The
        machine's timeline frees up immediately. No-op if not still active."""
        booking = self._store.get(booking_id)
        if booking is None:
            raise UnknownBooking(booking_id)
        if booking.status != BookingStatus.ACTIVE:
            return booking
        booking.status = BookingStatus.NO_SHOW
        self._store.update(booking)
        self._events.record(
            EventType.NO_SHOW_RELEASED,
            booking_id=booking_id,
            machine_id=booking.machine_id,
            member_id=booking.member_id,
        )
        return booking

    # ------------------------------------------------------------- suggestion
    def suggest_slot(
        self,
        duration: timedelta,
        *,
        member_id: "str | None" = None,
        earliest_start: "datetime | None" = None,
        machine_ids: "Sequence[str] | None" = None,
    ) -> SlotSuggestion:
        request = SlotRequest(
            member_id=member_id or "",
            duration=duration,
            earliest_start=to_utc(earliest_start) if earliest_start else self._clock(),
            machine_ids=tuple(machine_ids) if machine_ids else None,
        )
        return self._scheduler.suggest([request], self._store.all())[0]

    # ------------------------------------------------------------- validation
    def _validate(
        self, machine_id: str, member_id: str, start: datetime, end: datetime
    ) -> tuple[datetime, datetime]:
        machine = self._machines.get(machine_id)
        if machine is None:
            raise UnknownMachine(machine_id)
        if not machine.is_reserved:
            raise MachineNotReservable(machine_id)

        member = self._members.get(member_id)
        if member is None:
            raise UnknownMember(member_id)
        if not member.is_premium:
            raise MemberNotPremium(member_id)

        if start.tzinfo is None or end.tzinfo is None:
            raise InvalidWindow("datetimes must be timezone-aware")
        start_utc, end_utc = to_utc(start), to_utc(end)
        if end_utc <= start_utc:
            raise InvalidWindow("end must be after start")

        duration = end_utc - start_utc
        if duration < config.MIN_BOOKING_DURATION:
            raise InvalidWindow(f"minimum booking is {config.MIN_BOOKING_DURATION}")
        if duration > config.MAX_BOOKING_DURATION:
            raise InvalidWindow(f"maximum booking is {config.MAX_BOOKING_DURATION}")
        if start_utc < self._clock():
            raise InvalidWindow("cannot book a slot in the past")

        if not self._scheduler.is_available(
            machine_id, start_utc, end_utc, self._store.all()
        ):
            raise SlotUnavailable(machine_id)

        return start_utc, end_utc


def build_service(
    *,
    db_path: "str | None" = None,
    event_log_path: "str | None" = None,
    members: "Iterable[Member] | None" = None,
    clock: Callable[[], datetime] = utcnow,
    check_same_thread: bool = True,
) -> BookingService:
    """Wire up a persistent BookingService (SQLite store + JSONL event log).

    Shared by the API and the nudge engine so every consumer reads and writes
    the same booking state.
    """
    from members import DEFAULT_MEMBERS
    from store import SQLiteBookingStore

    store = SQLiteBookingStore(
        db_path or config.DB_PATH, check_same_thread=check_same_thread
    )
    log_path = event_log_path if event_log_path is not None else (config.EVENT_LOG_PATH or None)
    return BookingService(
        store,
        events=EventLog(log_path),
        members=members if members is not None else DEFAULT_MEMBERS,
        clock=clock,
    )
