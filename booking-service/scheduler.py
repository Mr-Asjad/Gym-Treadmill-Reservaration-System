"""Simple interval-overlap scheduler -- the default SCHEDULER_MODE.

This is the reference implementation. `cpsat_scheduler.py` (Phase 5) must expose
the same `Scheduler` interface so it is a drop-in swap. No CP-SAT / OR-Tools code
belongs in this file or leaks outward (CLAUDE.md "CP-SAT Toggle").

Both modes must produce a *valid* (non-overlapping) schedule. This one assigns
each request greedily to the earliest opening; CP-SAT mode is allowed to find a
globally *better* assignment.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol, Sequence

from models import (
    Booking,
    BookingStatus,
    DEFAULT_MACHINES,
    Machine,
    SlotRequest,
    SlotSuggestion,
    intervals_overlap,
)


class Scheduler(Protocol):
    """The contract shared by the simple and CP-SAT schedulers."""

    def is_available(
        self,
        machine_id: str,
        start: datetime,
        end: datetime,
        existing: Sequence[Booking],
        *,
        ignore_booking_id: str | None = None,
    ) -> bool: ...

    def suggest(
        self,
        requests: Sequence[SlotRequest],
        existing: Sequence[Booking],
    ) -> list[SlotSuggestion]: ...


def _blocking_intervals(
    machine_id: str,
    bookings: Sequence[Booking],
    ignore_booking_id: str | None = None,
) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for b in bookings:
        if b.machine_id != machine_id or b.status != BookingStatus.ACTIVE:
            continue
        if ignore_booking_id is not None and b.id == ignore_booking_id:
            continue
        out.append((b.start, b.end))
    out.sort()
    return out


class SimpleScheduler:
    def __init__(self, machines: Sequence[Machine] | None = None) -> None:
        machs = tuple(machines) if machines is not None else DEFAULT_MACHINES
        self._machines = machs
        self._reserved_ids = tuple(m.id for m in machs if m.is_reserved)

    def is_available(
        self,
        machine_id: str,
        start: datetime,
        end: datetime,
        existing: Sequence[Booking],
        *,
        ignore_booking_id: str | None = None,
    ) -> bool:
        if end <= start:
            return False
        for s, e in _blocking_intervals(machine_id, existing, ignore_booking_id):
            if intervals_overlap(start, end, s, e):
                return False
        return True

    def _earliest_on_machine(
        self,
        machine_id: str,
        duration: timedelta,
        earliest_start: datetime,
        intervals: list[tuple[datetime, datetime]],
    ) -> datetime:
        """Earliest `start >= earliest_start` on this machine that fits `duration`.

        Linear scan of the machine's sorted busy intervals, sliding a candidate
        past each blocker until a wide-enough gap appears.
        """
        candidate = earliest_start
        for s, e in intervals:
            if e <= candidate:
                continue
            if s - candidate >= duration:
                return candidate
            candidate = max(candidate, e)
        return candidate

    def suggest(
        self,
        requests: Sequence[SlotRequest],
        existing: Sequence[Booking],
    ) -> list[SlotSuggestion]:
        suggestions: list[SlotSuggestion] = []
        # Slots handed out earlier in this batch, so multi-request suggestions
        # stay non-overlapping with each other as well as with `existing`.
        held: dict[str, list[tuple[datetime, datetime]]] = {}

        for req in requests:
            candidate_ids = req.machine_ids or self._reserved_ids
            best_machine: str | None = None
            best_start: datetime | None = None

            for mid in candidate_ids:
                intervals = sorted(
                    _blocking_intervals(mid, existing) + held.get(mid, [])
                )
                start = self._earliest_on_machine(
                    mid, req.duration, req.earliest_start, intervals
                )
                if best_start is None or start < best_start:
                    best_machine, best_start = mid, start

            assert best_machine is not None and best_start is not None
            end = best_start + req.duration
            held.setdefault(best_machine, []).append((best_start, end))
            suggestions.append(
                SlotSuggestion(
                    machine_id=best_machine,
                    start=best_start,
                    end=end,
                    request=req,
                )
            )
        return suggestions


def build_scheduler(
    mode: str | None = None,
    machines: Sequence[Machine] | None = None,
) -> Scheduler:
    """Factory honouring config.SCHEDULER_MODE. The only place mode is branched."""
    import config

    resolved = (mode or config.SCHEDULER_MODE).strip().lower()
    if resolved not in config.VALID_SCHEDULER_MODES:
        raise ValueError(
            f"unknown SCHEDULER_MODE {resolved!r}; "
            f"expected one of {config.VALID_SCHEDULER_MODES}"
        )
    if resolved == "cpsat":
        try:
            from cpsat_scheduler import CpSatScheduler
        except ImportError as exc:  # pragma: no cover - Phase 5
            raise RuntimeError(
                "SCHEDULER_MODE=cpsat requires OR-Tools (Phase 5); "
                "install ortools or set SCHEDULER_MODE=simple"
            ) from exc
        return CpSatScheduler(machines)
    return SimpleScheduler(machines)
