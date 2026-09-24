"""The closed loop (CLAUDE.md Phase 4).

Compares live per-machine occupancy against the booking service's active
reservations and fires two kinds of soft event -- never a hard lockout:

  * **no-show release** -- a reservation's window has started, the grace period
    has passed, and the machine has never been occupied during the window. The
    booking is released (status -> NO_SHOW) so the timeline frees up.
  * **soft nudge** -- a reservation is about to start (within the nudge window)
    and someone is already on the machine. There is no identity system
    (CLAUDE.md "Out of Scope"), so any occupant in that pre-start window is
    treated as a non-reserver and nudged once.

Both are logged to the booking service's event log, which is what produces the
"schedule adherence %" metric (`adherence_stats`).

    engine = NudgeEngine(service)
    for now, occupancy in feed:            # occupancy: {machine_id: occupied}
        for ev in engine.tick(occupancy, now):
            notify(ev)                     # send the nudge / flag the no-show

`occupancy` comes from `integration.occupancy.OccupancyTracker`; a machine absent
from the map means "no CV data" and the engine takes no action on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterable, Mapping

import config
from events import EventType
from models import BookingStatus, utcnow
from service import BookingService


@dataclass(frozen=True)
class NudgeEngineEvent:
    kind: str            # "nudge" | "no_show_release"
    machine_id: str
    booking_id: str
    member_id: str
    at: datetime
    detail: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "machine_id": self.machine_id,
            "booking_id": self.booking_id,
            "member_id": self.member_id,
            "at": self.at.isoformat(),
            "detail": self.detail,
        }


class NudgeEngine:
    def __init__(
        self,
        service: BookingService,
        *,
        clock: Callable[[], datetime] = utcnow,
        grace_period: "timedelta | None" = None,
        nudge_window: "timedelta | None" = None,
    ) -> None:
        self._service = service
        self._clock = clock
        self._grace = grace_period if grace_period is not None else config.GRACE_PERIOD
        self._nudge_window = (
            nudge_window if nudge_window is not None else config.NUDGE_WINDOW
        )
        self._seen_occupied: set[str] = set()  # booking ids seen with an occupant in-window
        self._nudged: set[str] = set()         # booking ids already nudged
        self._released: set[str] = set()       # booking ids already released as no-show

    def prime_from_events(self, events: "Iterable[Mapping]") -> None:
        """Replay already-recorded nudge / no-show events so a freshly built
        engine does not re-fire them. The dashboard rebuilds the engine whenever
        its process restarts; without this a still-imminent booking would be
        nudged again."""
        for ev in events:
            booking_id = (ev.get("data") or {}).get("booking_id")
            if not booking_id:
                continue
            if ev.get("type") == EventType.NUDGE_FIRED.value:
                self._nudged.add(booking_id)
            elif ev.get("type") == EventType.NO_SHOW_RELEASED.value:
                self._released.add(booking_id)

    def tick(
        self, occupancy: Mapping[str, bool], now: "datetime | None" = None
    ) -> list[NudgeEngineEvent]:
        now = now or self._clock()
        emitted: list[NudgeEngineEvent] = []

        for machine in self._service.machines:
            if not machine.is_reserved:
                continue
            occupied = occupancy.get(machine.id)
            if occupied is None:
                continue  # no CV signal for this machine -- do nothing

            active = self._service.bookings(machine_id=machine.id, active_only=True)

            ongoing = next((b for b in active if b.start <= now < b.end), None)
            if ongoing is not None:
                if occupied:
                    self._seen_occupied.add(ongoing.id)
                elif (
                    ongoing.id not in self._seen_occupied
                    and ongoing.id not in self._released
                    and now - ongoing.start >= self._grace
                ):
                    self._service.release_no_show(ongoing.id)
                    self._released.add(ongoing.id)
                    late = int((now - ongoing.start).total_seconds())
                    emitted.append(
                        NudgeEngineEvent(
                            "no_show_release", machine.id, ongoing.id,
                            ongoing.member_id, now,
                            f"machine empty {late}s past reservation start",
                        )
                    )

            imminent = next(
                (b for b in active if b.start - self._nudge_window <= now < b.start),
                None,
            )
            if imminent is not None and occupied and imminent.id not in self._nudged:
                self._nudged.add(imminent.id)
                self._service.event_log.record(
                    EventType.NUDGE_FIRED,
                    booking_id=imminent.id,
                    machine_id=machine.id,
                    member_id=imminent.member_id,
                    reason="occupant_before_reservation",
                )
                until = int((imminent.start - now).total_seconds())
                emitted.append(
                    NudgeEngineEvent(
                        "nudge", machine.id, imminent.id, imminent.member_id, now,
                        f"occupant present {until}s before reservation start",
                    )
                )

        return emitted


@dataclass(frozen=True)
class AdherenceStats:
    total: int          # concluded bookings (honored + no-shows)
    honored: int
    no_shows: int
    cancelled: int

    @property
    def adherence_pct(self) -> float:
        return 100.0 if self.total == 0 else 100.0 * self.honored / self.total

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "honored": self.honored,
            "no_shows": self.no_shows,
            "cancelled": self.cancelled,
            "adherence_pct": round(self.adherence_pct, 1),
        }


def adherence_stats(
    service: BookingService, now: "datetime | None" = None
) -> AdherenceStats:
    """Schedule adherence over bookings whose window has started. A cancellation
    ahead of time is not counted against adherence; a no-show is."""
    now = now or utcnow()
    honored = no_shows = cancelled = 0
    for b in service.bookings():
        if b.status == BookingStatus.CANCELLED:
            cancelled += 1
            continue
        if b.start > now:
            continue  # not concluded yet
        if b.status == BookingStatus.NO_SHOW:
            no_shows += 1
        else:
            honored += 1
    return AdherenceStats(honored + no_shows, honored, no_shows, cancelled)
