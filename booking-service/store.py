"""Booking storage.

`InMemoryBookingStore` is used by the unit tests and can back the whole system
in a demo. `SQLiteBookingStore` is the persistent variant for the UI phases.
Both satisfy the `BookingStore` protocol, so the service never cares which it has.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Iterable, Protocol

from models import Booking, BookingStatus


class BookingStore(Protocol):
    def add(self, booking: Booking) -> None: ...
    def get(self, booking_id: str) -> "Booking | None": ...
    def update(self, booking: Booking) -> None: ...
    def all(self) -> list[Booking]: ...
    def for_machine(self, machine_id: str) -> list[Booking]: ...


class InMemoryBookingStore:
    def __init__(self, bookings: Iterable[Booking] = ()) -> None:
        self._by_id: dict[str, Booking] = {}
        for b in bookings:
            self.add(b)

    def add(self, booking: Booking) -> None:
        if booking.id in self._by_id:
            raise KeyError(f"duplicate booking id {booking.id!r}")
        self._by_id[booking.id] = booking

    def get(self, booking_id: str) -> "Booking | None":
        return self._by_id.get(booking_id)

    def update(self, booking: Booking) -> None:
        if booking.id not in self._by_id:
            raise KeyError(booking.id)
        self._by_id[booking.id] = booking

    def all(self) -> list[Booking]:
        return sorted(self._by_id.values(), key=lambda b: b.start)

    def for_machine(self, machine_id: str) -> list[Booking]:
        return [b for b in self.all() if b.machine_id == machine_id]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id         TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    member_id  TEXT NOT NULL,
    start      TEXT NOT NULL,
    end        TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class SQLiteBookingStore:
    def __init__(self, path: str = ":memory:", *, check_same_thread: bool = True) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=check_same_thread)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    @staticmethod
    def _to_booking(row: sqlite3.Row) -> Booking:
        return Booking(
            id=row["id"],
            machine_id=row["machine_id"],
            member_id=row["member_id"],
            start=datetime.fromisoformat(row["start"]),
            end=datetime.fromisoformat(row["end"]),
            status=BookingStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def add(self, booking: Booking) -> None:
        try:
            self._conn.execute(
                "INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    booking.id,
                    booking.machine_id,
                    booking.member_id,
                    booking.start.isoformat(),
                    booking.end.isoformat(),
                    booking.status.value,
                    booking.created_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise KeyError(f"duplicate booking id {booking.id!r}") from exc
        self._conn.commit()

    def get(self, booking_id: str) -> "Booking | None":
        row = self._conn.execute(
            "SELECT * FROM bookings WHERE id = ?", (booking_id,)
        ).fetchone()
        return self._to_booking(row) if row is not None else None

    def update(self, booking: Booking) -> None:
        cur = self._conn.execute(
            "UPDATE bookings SET machine_id=?, member_id=?, start=?, end=?, "
            "status=?, created_at=? WHERE id=?",
            (
                booking.machine_id,
                booking.member_id,
                booking.start.isoformat(),
                booking.end.isoformat(),
                booking.status.value,
                booking.created_at.isoformat(),
                booking.id,
            ),
        )
        if cur.rowcount == 0:
            raise KeyError(booking.id)
        self._conn.commit()

    def all(self) -> list[Booking]:
        rows = self._conn.execute("SELECT * FROM bookings ORDER BY start").fetchall()
        return [self._to_booking(r) for r in rows]

    def for_machine(self, machine_id: str) -> list[Booking]:
        rows = self._conn.execute(
            "SELECT * FROM bookings WHERE machine_id = ? ORDER BY start", (machine_id,)
        ).fetchall()
        return [self._to_booking(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
